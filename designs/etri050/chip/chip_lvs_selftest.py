#!/usr/bin/env python3
"""Show that chip_lvs.py finds what it should: the chip as built must match, and every case below,
one error put into the layout or into the reference, must not.

Layout cases change a copy of pdkv_Top.gds (cells or top-level routing); reference cases change the
circuit chip_lvs.py builds (its tables, a block netlist copy, the pad pin table, the anchors). Shorts
between the VSS branches or between a force and its sense line are not among them on purpose: the
branches meet in the PVSS port here and force and sense are one net, so those are chip_check.py's to
find (section 5, star nets).

usage: python3 designs/etri050/chip/chip_lvs_selftest.py      (exit 0 when every case behaves)
"""
import json
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chip_lvs as C  # noqa: E402

GDS = HERE / "build/pdkv_Top.gds"
NETS = json.load(open(HERE / "build/pdkv_nets.json"))["nets"]
LAY = {"m1": 32, "m2": 34, "m3": 36}


def point(net, at):
    p = [p for p in NETS[net] if p["at"] == at][0]
    return p["layer"], kdb.DPoint(p["x"], p["y"])


def edit_gds(fn):
    """Copy of the chip GDS changed by fn(layout, top) -> path."""
    ly = kdb.Layout()
    ly.read(str(GDS))
    fn(ly, ly.top_cell())
    path = Path(tempfile.mkdtemp()) / "pdkv_Top.gds"
    ly.write(str(path))
    return path


def drop_layer(cell, layer, first_only=False):
    """Clear a layer in a cell and the cells below it (or erase its first shape there)."""
    def fn(ly, top):
        c = ly.cell(cell)
        li = ly.layer(layer, 0)
        hit = [s for s in (ly.cell(i).shapes(li) for i in [c.cell_index()] + list(c.called_cells())) if not s.is_empty()]
        if not hit:
            raise SystemExit(f"selftest: {cell} has nothing on layer {layer}")
        if first_only:
            hit[0].erase(next(hit[0].each()))
        else:
            for s in hit:
                s.clear()
    return fn


def drop_gate_finger(cell):
    """Remove the POLY1 of one gate finger (the first POLY1 shape over ACT) in a flat cell."""
    def fn(ly, top):
        c = ly.cell(cell)
        act = kdb.Region(c.shapes(ly.layer(11, 0)))
        poly = c.shapes(ly.layer(12, 0))
        for s in poly.each():
            if not (kdb.Region(s.polygon) & act).is_empty():
                poly.erase(s)
                return
        raise SystemExit(f"selftest: no gate in {cell}")
    return fn


def drop_route(net, at):
    """Delete the top-level shape under a probe point of pdkv_nets.json (opens that route)."""
    def fn(ly, top):
        layer, pt = point(net, at)
        shapes = top.shapes(ly.layer(LAY[layer], 0))
        q = pt.to_itype(ly.dbu)
        hit = [s for s in shapes.each() if s.polygon is not None and s.polygon.inside(q)]
        if not hit:
            raise SystemExit(f"selftest: no top-level {layer} shape at {net} {at}")
        for s in hit:
            shapes.erase(s)
    return fn


def cut_at_port(pad):
    """Delete the top-level metal touching a pad's core port (the route no longer reaches the pad)."""
    def fn(ly, top):
        rect = [p["rect"] for p in json.load(open(HERE / "build/pad_pins.json"))["pads"] if p["pad"] == pad][0]
        box = kdb.DBox(*rect).to_itype(ly.dbu)
        n = 0
        for layer in LAY.values():
            shapes = top.shapes(ly.layer(layer, 0))
            for s in [s for s in shapes.each() if s.polygon is not None and s.polygon.touches(box)]:
                shapes.erase(s)
                n += 1
        if not n:
            raise SystemExit(f"selftest: no top-level metal at the port of {pad}")
    return fn


def m2_off_port(pad):
    """Delete only the top-level metal2 at a pad's port: another metal may still cross the rectangle."""
    def fn(ly, top):
        rect = [p["rect"] for p in json.load(open(HERE / "build/pad_pins.json"))["pads"] if p["pad"] == pad][0]
        box = kdb.DBox(*rect).to_itype(ly.dbu)
        shapes = top.shapes(ly.layer(34, 0))
        hit = [s for s in shapes.each() if s.polygon is not None and s.polygon.touches(box)]
        if not hit:
            raise SystemExit(f"selftest: no top-level metal2 at the port of {pad}")
        for s in hit:
            shapes.erase(s)
    return fn


def drop_at(layer, x, y):
    """Delete the top-level shape on a layer under a die point (um)."""
    def fn(ly, top):
        q = kdb.DPoint(x, y).to_itype(ly.dbu)
        shapes = top.shapes(ly.layer(layer, 0))
        hit = [s for s in shapes.each() if s.polygon is not None and s.polygon.inside(q)]
        if not hit:
            raise SystemExit(f"selftest: no top-level shape on {layer} at ({x}, {y})")
        for s in hit:
            shapes.erase(s)
    return fn


def open_ring(cell, box):
    """Flatten a cell and cut ACT along a box (um, cell coordinates): opens the PNP collector ring."""
    def fn(ly, top):
        c = ly.cell(cell)
        c.flatten(True)
        act = c.shapes(ly.layer(11, 0))
        r = kdb.Region(act) - kdb.Region(kdb.DBox(*box).to_itype(ly.dbu))
        act.clear()
        act.insert(r)
    return fn


def add_box(layer, box):
    def fn(ly, top):
        top.shapes(ly.layer(layer, 0)).insert(kdb.DBox(*box).to_itype(ly.dbu))
    return fn


def bridge(net_a, at_a, net_b, at_b):
    """A metal3 strap from one probe point to another (a short)."""
    def fn(ly, top):
        (_, a), (_, b) = point(net_a, at_a), point(net_b, at_b)
        box = kdb.DBox(a.x - 0.6, min(a.y, b.y) - 0.6, a.x + 0.6, max(a.y, b.y) + 0.6)
        top.shapes(ly.layer(36, 0)).insert(box.to_itype(ly.dbu))
    return fn


class patched:
    """Set module attributes of chip_lvs for one case."""

    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(C, k)
            setattr(C, k, v)

    def __exit__(self, *a):
        for k, v in self.old.items():
            setattr(C, k, v)


def blocks_with(inst, changes):
    base = C.chip_blocks

    def fn():
        out = []
        for i, c, conn in base():
            if i == inst:
                conn = dict(conn)
                for k, v in changes.items():
                    if v is None:
                        conn.pop(k)
                    else:
                        conn[k] = v
            out.append((i, c, conn))
        return out
    return fn


def sch_with(block, old, new):
    path = C.SCH[block]
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"selftest: '{old}' not once in {path.name}")
    tmp = Path(tempfile.mkdtemp()) / path.name
    tmp.write_text(text.replace(old, new))
    return dict(C.SCH, **{block: tmp})


def pins_with(swap=None, force=None):
    """Pad pins with two port rectangles swapped, or one port declared a force (PAD) port."""
    base = C.pad_pins

    def fn():
        rows = base()
        rect = {n: r for n, _, _, r, _ in rows}
        out = []
        for n, net, pad, r, kind in rows:
            if swap and n in swap:
                r = rect[swap[1] if n == swap[0] else swap[0]]
            if n == force:
                kind = "PAD"
            out.append((n, net, pad, r, kind))
        return out
    return fn


def nodes_swapped(i, j):
    """The CBCM structure anchors of cells i and j exchanged (as if the two structures were swapped)."""
    base = C.cbcm_nodes

    def fn():
        rows = base()
        pos = {k: (lay, at) for k, lay, at in rows}
        return [(k, *(pos[j] if k == i else pos[i] if k == j else pos[k])) for k, _, _ in rows]
    return fn


LAYOUT_CASES = [
    ("heater RES marker removed", drop_layer("heater", 51)),
    ("LVSD of one RO resistor removed", drop_layer("rores", 60, first_only=True)),
    ("PIP CAP marker removed", drop_layer("cbcm", 53)),
    ("PNP BJT marker removed", drop_layer("pnp10", 56)),
    ("one MOS-C gate finger removed", drop_gate_finger("mosc")),
    ("col_sel0 channel track cut", drop_route("COL_SEL0", "channel track")),
    ("col_sel0 and col_selb0 tracks strapped", bridge("COL_SEL0", "channel track", "COL_SELB0", "channel track")),
    ("HT line cut off its pad (E7)", cut_at_port("E7")),
    ("RO_EN5 riser removed", drop_route("RO_EN5", "gap riser en5")),
    ("AG metal2 removed at its pad (W7), metal3 still crossing", m2_off_port("W7")),
    ("PNP1 / L-split VSS branch cut at the PVSS port", drop_at(34, 1450.0, 1063.0)),
    ("resistor RO VSS strap removed", drop_at(36, 900.0, 1170.0)),
    ("PIP LVSD strip removed", drop_layer("cbcm", 60)),
    ("PNP collector rings opened", open_ring("pnp10", (0.0, 24.0, 11.0, 25.0))),
    ("DIODE marker over the CBCM n+ area cell", add_box(57, (1260.55, 533.85, 1280.95, 554.25))),
]
REFERENCE_CASES = [
    ("heater W 21 um in the reference", dict(HEATER_WL=(21.0, 120.0))),
    ("PIP 30 x 31 um in the reference", dict(PIP_WL=(30.0, 31.0))),
    ("PNP emitter 25 um2 in the reference", dict(PNP_AE=25.0)),
    ("PIP plates swapped in the reference", dict(PIP_PLATES=("VSS", "ND1"))),
    ("ro_en[0] and ro_en[1] swapped", dict(chip_blocks=blocks_with("ctrl", {"ro_en[0]": "RO_EN1", "ro_en[1]": "RO_EN0"}))),
    ("cbcm_en[0] and cbcm_en[1] swapped", dict(chip_blocks=blocks_with("ctrl", {"cbcm_en[0]": "CBCM_EN1",
                                                                              "cbcm_en[1]": "CBCM_EN0"}))),
    ("ro_in[3] left open", dict(chip_blocks=blocks_with("ctrl", {"ro_in[3]": None}))),
    ("L-split drains swapped", dict(chip_blocks=blocks_with("lsplit", {"LD1F": "D2", "LD2F": "D1"}))),
    ("array: one device W 9 -> 8.4 um", dict(SCH=sch_with("karray", "M1 D0 G0 SRC VSS nfet W=9u L=0.6u",
                                                         "M1 D0 G0 SRC VSS nfet W=8.4u L=0.6u"))),
    ("LD1F and LD2F pad ports swapped", dict(pad_pins=pins_with(swap=("LD1F", "LD2F")))),
    ("SDI and SCK pad ports swapped", dict(pad_pins=pins_with(swap=("SDI", "SCK")))),
    ("LD1S sensed on D2", dict(PAD_NET=dict(C.PAD_NET, LD1S="D2"))),
    ("cbcm_en[2] and cbcm_en[3] swapped", dict(chip_blocks=blocks_with("ctrl", {"cbcm_en[2]": "CBCM_EN3",
                                                                              "cbcm_en[3]": "CBCM_EN2"}))),
    ("array rows 0 and 1 swapped", dict(chip_blocks=blocks_with("ctrl", {
        "row_sel[0]": "ROW_SEL1", "row_sel[1]": "ROW_SEL0", "row_selb[0]": "ROW_SELB1", "row_selb[1]": "ROW_SELB0"}))),
    ("CBCM structures 2 and 3 swapped", dict(cbcm_nodes=nodes_swapped(2, 3))),
    ("LD1S taken for a force port", dict(pad_pins=pins_with(force="LD1S"))),
]


def reason(rep):
    """The line that says why a case failed: a problem found before the comparison, else the first
    unmatched item."""
    for line in rep:
        if "; problems: " in line:
            return line.split("; problems: ", 1)[1]
    return rep[-2].strip() if len(rep) > 1 else ""


def main():
    ok, rep = C.lvs(GDS)
    print(f"{'MATCH' if ok else 'MISMATCH':9s} the chip as built")
    good = ok
    for name, fn in LAYOUT_CASES:
        hit, rep = C.lvs(edit_gds(fn))
        print(f"{'MATCH' if hit else 'MISMATCH':9s} {name}: {reason(rep)}"[:170])
        good &= not hit
    for name, kw in REFERENCE_CASES:
        with patched(**kw):
            hit, rep = C.lvs(GDS)
        print(f"{'MATCH' if hit else 'MISMATCH':9s} {name}: {reason(rep)}"[:170])
        good &= not hit
    n = len(LAYOUT_CASES) + len(REFERENCE_CASES)
    print(f"selftest: the chip matches and {n} of {n} broken cases mismatch" if good else "selftest: FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
