#!/usr/bin/env python3
"""Write the pad ring GDS with ETRI's own GPIO cells, at the places Magic gave them.

The kit draws the pad ring in Magic (pads_ETRI/MPW_PAD_28Pin_IO.mag, cells in pads_ETRI/GDS_Magic) and
writes it with the GPIO style lambda=0.30(ETRI-G), as its generate_chip.sh does. Those Magic cells are
redrawn copies of ETRI's GDS, not the GDS itself, and they differ from it:

  PANA       its P+/N-well ESD diodes (pdiode10, 12 per cell) have no N-well paint, so the GDS has
             none: each diode's p+ anode on the pad becomes a substrate contact (the pad is tied to
             the substrate); ETRI's GPIO document gives PANA N and P diodes
  all cells  NSD / PSD drawn again from Magic's diffusion types (other extents), and no RES, LVSD,
             DIODE or ESDD

This script keeps Magic's ring (which cell goes where, from pad_ring.py) and only swaps the cell
contents: every cell of the ring that ETRI's GPIO library has (PANA, PIC, POB4, PVDD, PVSS, PCORNER,
IOFILLER50) is copied unchanged from that library; the kit's own IOFILLER18 (not in the library)
stays as Magic wrote it, flattened into one cell. It checks that every instance and transform is
kept and that each copied cell equals the library cell layer by layer.

usage: python3 pad_gds.py --magic build/pdkv_Pad_magic.gds --gpio <kit>/pads_ETRI/GDS/ETRI_NSPL_GPIO_250610.gds
                          --out build/pdkv_Pad.gds
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import klayout.db as kdb


def layer_regions(ly, cell):
    out = {}
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        r = kdb.Region(cell.begin_shapes_rec(li))
        if not r.is_empty():
            out[(info.layer, info.datatype)] = r.merged()
    return out


def build(magic: Path, gpio: Path, out: Path):
    m = kdb.Layout()
    m.read(str(magic))
    mtop = m.top_cell()
    o = kdb.Layout()
    o.read(str(gpio))                                  # the library: its cells keep their names
    lib_top = [c for c in o.top_cells()]
    if abs(o.dbu - m.dbu) > 1e-9:
        raise SystemExit(f"database units differ: {gpio} {o.dbu}, {magic} {m.dbu}")
    for li in m.layer_indexes():
        if mtop.shapes(li).size():
            raise SystemExit(f"{magic}: shapes in the top cell on {m.get_info(li)}; this script expects instances only")
    top = o.create_cell(mtop.name)
    used = Counter(i.cell.name for i in mtop.each_inst())
    source = {}
    for name in used:
        if o.cell(name) is not None and o.cell(name).cell_index() not in [c.cell_index() for c in lib_top]:
            source[name] = "ETRI " + gpio.name
            continue
        flat = o.create_cell(name)                     # kit-only cell: Magic's drawing, flattened
        tmp = kdb.Layout()
        tmp.dbu = m.dbu
        t = tmp.create_cell(name)
        t.copy_tree(m.cell(name))
        tmp.flatten(t.cell_index(), -1, True)
        flat.copy_shapes(t)
        source[name] = "Magic (kit cell, flattened)"
    for inst in mtop.each_inst():
        a = inst.cell_inst.dup()
        a.cell_index = o.cell(inst.cell.name).cell_index()
        top.insert(a)
    for c in lib_top:                                  # the library's own top cell and what only it uses
        o.prune_cell(c.cell_index(), -1)
    if [c.name for c in o.top_cells()] != [mtop.name]:
        raise SystemExit(f"top cells after the swap: {[c.name for c in o.top_cells()]}")

    # checks: the same instances, transforms and cells; the library cells unchanged
    got = Counter(i.cell.name for i in top.each_inst())
    if got != used:
        raise SystemExit(f"instances differ: {used} -> {got}")
    tm = sorted((i.cell.name, str(i.cell_inst.trans)) for i in mtop.each_inst())
    to = sorted((i.cell.name, str(i.cell_inst.trans)) for i in top.each_inst())
    if tm != to:
        raise SystemExit("instance transforms differ")
    lib = kdb.Layout()
    lib.read(str(gpio))
    for name, src in source.items():
        if src.startswith("ETRI"):
            a, b = layer_regions(o, o.cell(name)), layer_regions(lib, lib.cell(name))
            bad = [k for k in set(a) | set(b) if not (a.get(k, kdb.Region()) ^ b.get(k, kdb.Region())).is_empty()]
            if bad:
                raise SystemExit(f"{name}: differs from the library on {bad}")
    out.parent.mkdir(parents=True, exist_ok=True)
    o.write(str(out))
    return used, source


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--magic", type=Path, required=True)
    ap.add_argument("--gpio", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    used, source = build(args.magic, args.gpio, args.out)
    print(f"wrote {args.out}: {sum(used.values())} instances, cells from " +
          ", ".join(f"{n} x{used[n]} {source[n]}" for n in sorted(used)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
