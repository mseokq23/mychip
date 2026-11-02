"""Wiring capacitance of every net of the chip core, from the drawn GDS and the rule document's table.

The nets are the ones chip_lvs.py extracts and matches (named after the reference), so the values can be
added to the transistor netlist chip_post.py simulates. The devices' own capacitance (junctions, gate,
overlap) is in their models; this adds what the wiring draws, with the rule document v1.1 table 5.5
(typical area fF/um2 and fringe fF/um, as designs/etri050/cbcm/cbcm_c.py uses them):

  upper plate  every metal shape over the nearest conductor below it that belongs to another net
               (metal, POLY2, POLY1 or active: "Metal n to Metal m", "... to Poly/Active"), field where
               there is none; its edges the same way along a 5 nm strip just outside them (fringe)
  lower plate  the net's metal, poly and active under another net's metal, unless a layer between shields
               it, with the upper metal's value (so each overlap counts for both nets)
  field poly   POLY1 outside active: "Poly to field" area and fringe

Not counted: coupling between neighbours on one layer (the table has no value for it; lateral() gives
an upper estimate for brackets), POLY2 over field (no value: resistor heads, the resistor bodies, which
belong to no net), and gate / PIP plates (devices). Active that no device terminal claims (CBCM cells 6
and 7, bare n+ junctions) counts as the net whose contacts land on it. Every coupling goes to ground,
as for ro_post.py: the transistor netlist then sees each net's whole wiring load.

Checked against the block extractors that use the same table (cbcm_c.py, ro_post.py): every RO bank
node (r0-r4, t0-t4) and every CBCM node and clock net comes out the same to 0.01 fF (2026-11-02).

r_bound(): an upper bound on the resistance between any two points of a net's metal (rule document
5.2 / 5.3 maximum values; the contacts down to poly and diffusion belong to the cells, the same in every
copy of a cell): every metal shape is at least the layer's minimum width (8.MET1.W 0.8, 10.MET2.W 1.0,
12.MET3.W 1.2 um), so a path has at most area / w_min^2 squares on each layer, and it passes each via
cut of the net at most once.

usage: from chip_rc import wiring; caps = wiring(keep)   (keep: chip_lvs.lvs(..., named=True, keep=True))
       python3 chip_rc.py [--gds build/pdkv_Top.gds]   prints the largest values and the time
"""
import argparse
import sys
import time
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "cbcm"))
from cbcm_c import DOC  # noqa: E402  rule document 5.5 values

STRIP = 0.005                                  # um, the outside strip that finds an edge's lower plate
STACK = ["m3", "m2", "m1", "poly2", "poly1", "act"]          # conductors, top to bottom
GROUP = {"m2": "m2", "m1": "m1", "poly2": "pa", "poly1": "pa", "act": "pa"}
GDS = {"m1": 32, "m2": 34, "m3": 36, "poly1": 12, "poly2": 13, "act": 11}
# the extraction's layers that hold a net's shapes, per conductor of the stack
OWN = {"m3": ("m3",), "m2": ("m2",), "m1": ("m1",), "poly2": ("r_term", "pip_pos"),
       "poly1": ("pl1", "pip_pl1"),
       "act": ("nisd", "pisd", "ntap", "ptap", "pnp_e", "pnp_bc", "pnp_c")}


def wiring(keep, skip=("VDD", "VSS"), log=None):
    """{reference net name: F} for every matched net of the core but those in skip."""
    lv, L, ly, top, names = keep["lv"], keep["L"], keep["ly"], keep["top"], keep["names"]
    li = {k: ly.layer(n, 0) for k, n in GDS.items()}
    reg = {}
    for k, regs in OWN.items():
        reg[k] = [L[r] if r in L else lv.layer_by_name(r) for r in regs]
    # Active that no device terminal claims (CBCM cells 6 and 7: bare n+ junctions, no device in the
    # deck) belongs to the net whose contacts land on it, not to "another net" under that net's metal.
    known = L["poly1"]
    for x in reg["act"]:
        known = known + x
    bare = kdb.Region([p for p in (L["act"] - known).each()])
    d = round(STRIP / ly.dbu)
    um = ly.dbu
    margin = round(1.0 / ly.dbu)
    circ = next(lv.netlist().each_circuit_top_down())
    out = {}
    t0 = time.time()
    for net in circ.each_net():
        nm = names.get(net.cluster_id)
        if nm is None or nm in skip:
            continue
        own = {}
        box = kdb.Box()
        for k, regs in reg.items():
            r = kdb.Region()
            for x in regs:
                r += lv.shapes_of_net(net, x, True)
            own[k] = r.merged()
            box += own[k].bbox()
        if box.empty():
            continue
        box = box.enlarged(margin)
        cont = lv.shapes_of_net(net, L["cont"], True)
        if not cont.is_empty():
            own["act"] = (own["act"] + bare.interacting(cont)).merged()
        loc = {k: kdb.Region(top.begin_shapes_rec_touching(li[k], box)).merged() for k in STACK}
        others = {k: loc[k] - own[k] for k in STACK}
        c = 0.0                                               # fF

        def add(key, mode, region):
            nonlocal c
            if region.is_empty():
                return
            area = region.area() * um * um
            c += DOC[key][0] * area if mode == "area" else DOC[key][1] * area / (d * um)

        # the net's metal as the upper plate
        for k in ("m3", "m2", "m1"):
            s = own[k]
            if s.is_empty():
                continue
            for mode, base in (("area", s), ("fringe", (s.sized(d) - s).merged())):
                rest = base
                for low in STACK[STACK.index(k) + 1:]:
                    if rest.is_empty():
                        break
                    add((k, GROUP[low]), mode, rest & others[low])
                    rest = rest - loc[low]
                add((k, "field"), mode, rest)
        # field poly
        p = own["poly1"]
        if not p.is_empty():
            add(("poly", "field"), "area", p - loc["act"])
            add(("poly", "field"), "fringe", ((p.sized(d) - p) - loc["act"]))
        # the net's conductors as the lower plate under other nets' metal
        for low in ("m2", "m1", "poly2", "poly1", "act"):
            mine = own[low]
            if mine.is_empty():
                continue
            for up in STACK[:STACK.index(low)]:
                if up not in ("m3", "m2", "m1"):
                    continue
                shield = kdb.Region()
                for mid in STACK[STACK.index(up) + 1:STACK.index(low)]:
                    shield += loc[mid]
                base = (mine - shield) if not shield.is_empty() else mine
                if base.is_empty():
                    continue
                o = others[up]
                add((up, GROUP[low]), "area", base & o)
                add((up, GROUP[low]), "fringe", base & (o.sized(d) - o))
        out[nm] = c * 1e-15
    if log is not None:
        log.append(f"wiring capacitance of {len(out)} nets in {time.time() - t0:.0f} s")
    return out


# Same-layer neighbours (no table value): the parallel-plate value eps t / s along every facing edge
# closer than FACE, eps = 4 eps0 and the metal thicknesses of the PDK's own PEX stack
# (Calibre/PEX/MIPT/typical.mipt: MET1 0.60, MET2 0.68, MET3 0.88 um, oxide eps 4). For lines 0.8 to
# 3 um apart at these heights it is above the Sakurai-Tamaru coupling of two lines over a ground plane
# (IEEE Trans. Electron Devices 30(2), 1983), so it serves as an upper estimate.
EPS = 4 * 8.854e-3                              # fF/um
THICK = {"m1": 0.60, "m2": 0.68, "m3": 0.88}
FACE = 3.0                                      # um


def _named(keep, wanted):
    lv, names = keep["lv"], keep["names"]
    circ = next(lv.netlist().each_circuit_top_down())
    return [(names[n.cluster_id], n) for n in circ.each_net() if names.get(n.cluster_id) in wanted]


def lateral(keep, wanted):
    """{reference net name: F}: same-layer coupling of each net in wanted to all other nets (upper
    estimate, see above)."""
    lv, L, ly, top = keep["lv"], keep["L"], keep["ly"], keep["top"]
    um = ly.dbu
    dist = round(FACE / um)
    out = {}
    for nm, net in _named(keep, wanted):
        c = 0.0
        for k in ("m1", "m2", "m3"):
            own = lv.shapes_of_net(net, L[k], True).merged()
            if own.is_empty():
                continue
            box = own.bbox().enlarged(dist + 1)
            other = kdb.Region(top.begin_shapes_rec_touching(ly.layer(GDS[k], 0), box)).merged() - own
            for ep in own.separation_check(other, dist, False, kdb.Region.Projection).each():
                s = ep.distance() * um
                if s > 0:
                    c += EPS * THICK[k] / s * ep.first.length() * um
        out[nm] = c * 1e-15
    return out


RS_MAX = {"m1": 0.10, "m2": 0.10, "m3": 0.06}  # ohm/sq, rule document 5.2 max
W_MIN = {"m1": 0.8, "m2": 1.0, "m3": 1.2}      # um, 8.MET1.W, 10.MET2.W, 12.MET3.W
R_CUT_MAX = {"v1": 3.0, "v2": 2.5}             # ohm per cut, 5.3 max


def r_bound(keep, wanted):
    """{reference net name: ohm}: upper bound on the wire resistance between two points of the net."""
    lv, L, ly = keep["lv"], keep["L"], keep["ly"]
    um2 = ly.dbu * ly.dbu
    out = {}
    for nm, net in _named(keep, wanted):
        r = 0.0
        for k, rs in RS_MAX.items():
            a = lv.shapes_of_net(net, L[k], True).merged().area() * um2
            r += rs * a / W_MIN[k] ** 2
        for k, rc in R_CUT_MAX.items():
            r += rc * lv.shapes_of_net(net, L[k], True).merged().count()
        out[nm] = r
    return out


GATE = {"NFET": (2.9739, 0.3134), "PFET": (2.9624, 0.2138)}   # rule document 5.5 poly gate: fF/um2, fF/um


def pob4_input(gds):
    """What the core's OUT drives: the POB4 pad cell (ETRI GPIO) as drawn in gds, extracted with
    chip_lvs.extract. Returns the MOS whose gate is the A port (the input stage) with their nets named
    A, X (the stage's output), VDD, VSS and the wells, the gates on X (the output stage) as one
    capacitance (rule document 5.5 gate area and fringe), and the wiring of A and X inside the cell."""
    import chip_lvs
    src = kdb.Layout()
    src.read(str(gds))
    cell = src.cell("POB4")
    a_at = None
    it = cell.begin_shapes_rec(src.layer(44, 0))              # MET2TXT, the port label
    while not it.at_end():
        if it.shape().is_text() and it.shape().text.string == "A":
            a_at = it.shape().text.transformed(it.trans()).position()
        it.next()
    if a_at is None:
        raise SystemExit("POB4: no A label")
    ly = kdb.Layout()
    ly.dbu = src.dbu
    top = ly.create_cell("POB4")
    top.copy_tree(cell)
    ly.flatten(top.cell_index(), -1, True)
    lv, L = chip_lvs.extract(ly, top, [], (), ())
    circ = next(lv.netlist().each_circuit_top_down())
    a = lv.probe_net(L["m2"], kdb.DPoint(a_at.x * ly.dbu, a_at.y * ly.dbu))
    if a is None:
        raise SystemExit("POB4: nothing under the A label")

    def term(d, t):
        return d.net_for_terminal(d.device_class().terminal_id(t))

    stage = [d for d in circ.each_device() if d.device_class().name in ("NFET", "PFET")
             and term(d, "G").cluster_id == a.cluster_id]
    outs = {}
    for d in stage:
        for t in ("S", "D"):
            outs.setdefault(term(d, t).cluster_id, set()).add(d.device_class().name)
    x = [c for c, kinds in outs.items() if kinds == {"NFET", "PFET"}]
    if len(x) != 1:
        raise SystemExit(f"POB4: input stage output is not one net ({len(x)})")
    x = x[0]
    rails = {k: {term(d, t).cluster_id for d in stage if d.device_class().name == k for t in ("S", "D")} - {x}
             for k in ("NFET", "PFET")}
    if any(len(r) != 1 for r in rails.values()) or rails["NFET"] == rails["PFET"]:
        raise SystemExit(f"POB4: input stage is not one inverter ({rails})")
    devs = []
    for d in stage:
        cls = d.device_class().name
        rail = "VSS" if cls == "NFET" else "VDD"
        t = {k: ("X" if term(d, k).cluster_id == x else rail) for k in ("S", "D")}
        p = {k: d.parameter(k) for k in ("W", "L", "AS", "AD", "PS", "PD")}
        devs.append((cls, t, p))
    c_x = 0.0
    n_x = 0
    for d in circ.each_device():
        if d.device_class().name in GATE and d.net_for_terminal(d.device_class().terminal_id("G")).cluster_id == x:
            area, fringe = GATE[d.device_class().name]
            c_x += area * d.parameter("W") * d.parameter("L") + fringe * 2 * d.parameter("W")
            n_x += 1
    keep = {"lv": lv, "L": L, "ly": ly, "top": top, "names": {a.cluster_id: "A", x: "X"}}
    w = wiring(keep, skip=())
    return {"devices": devs, "c_x_gates": c_x * 1e-15, "n_x_gates": n_x, "wire_a": w.get("A", 0.0),
            "wire_x": w.get("X", 0.0)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", default=str(HERE / "build/pdkv_Top.gds"))
    a = ap.parse_args(argv)
    import chip_lvs
    good, rep, nl, keep = chip_lvs.lvs(Path(a.gds), named=True, keep=True)
    if not good:
        print("\n".join(rep))
        return 1
    log = []
    caps = wiring(keep, log=log)
    print(log[0])
    for nm, c in sorted(caps.items(), key=lambda x: -x[1])[:25]:
        print(f"{c * 1e15:9.1f} fF  {nm}")
    tot = sum(caps.values())
    print(f"total {tot * 1e12:.2f} pF over {len(caps)} nets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
