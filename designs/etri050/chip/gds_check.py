#!/usr/bin/env python3
"""Submission checks of the chip GDS that no DRC deck makes: the file, its layers, grid, cells and labels.

  file     one top cell, pdkv_Top; database unit 1 nm; its extent the CHIPBOUNDARY (layer 0) of
           1.9 x 1.9 mm with the origin at its lower left corner
  layers   every layer / datatype is in the PDK's layer map (NSPL_..._V1p1.layermap, all datatype 0),
           and none of the map's layers that are not a designer's: NODRC (58: Calibre leaves its area
           out of every check), KEY (1) and DUMMY0-9 (100-109)
  grid     every vertex of every shape and every placement on the 0.01 um design grid (rule document
           3.3; ETRI's Calibre deck checks OFFGRID per layer, the kit's KLayout deck does not); text
           positions are no geometry and are only counted
  shapes   every edge orthogonal or at 45 degrees (rule document 3.3); paths with a width that is an
           even number of grid steps, extensions on the grid and no round ends (else their outline
           leaves the grid)
  placements  magnification 1 and rotations of 0 / 90 / 180 / 270 degrees only; array pitches on the grid
  arrays   no degenerate cell array (AREF of a single element, or a zero pitch along a repeated
           direction: some tools refuse to read those; pad_gds.py writes ETRI's 1 x 1 arrays as single
           placements)
  cells    every cell either one of ETRI's GPIO library (ETRI_NSPL_GPIO_250610.gds) with the library's
           geometry, or ours; ours listed with whether their names carry the design's prefix (pdkv_):
           cells of several designs may be merged by name, and a short generic name can meet another
           design's (a question to ETRI, not a rule; the kit's pong_pt1, made in MPW2025, went in with
           unprefixed cells, IOFILLER18 among them, as ours does)
  labels   texts in the top cell on the label layers that ETRI's LVS deck reads (TEXT DEPTH PRIMARY:
           POLY1TXT 41, MET1TXT 42, MET2TXT 44, MET3TXT 46, PADTXT 47) would name nets: none is drawn, so
           any fails (pad name labels, if ETRI wants them, would be listed here as expected); the texts on
           other layers and inside cells are counted

usage: python3 designs/etri050/chip/gds_check.py [--gds build/pdkv_Top.gds] [--gpio <ETRI GPIO gds>]
       exit 0 when nothing fails (the cell-name list is information)
"""
import argparse
import collections
import os
import sys
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
LAYERMAP_NAMES = {0: "CHIPBOUNDARY", 1: "KEY", 2: "NWELL", 3: "PWELL", 4: "HNWELL", 5: "HPWELL", 6: "DWELL",
                  7: "DNWELL", 8: "DPWELL", 11: "ACT", 12: "POLY1", 13: "POLY2", 14: "NSD", 15: "PSD", 16: "FVTN",
                  17: "FVTP", 18: "VTN", 19: "VTP", 20: "NHRI", 21: "PHRI", 22: "NPI", 23: "PPI", 24: "NDRIFT",
                  25: "PDRIFT", 26: "ESDI", 27: "TGOX", 28: "JISO", 29: "TISO", 31: "CONT", 32: "MET1", 33: "VIA1",
                  34: "MET2", 35: "VIA2", 36: "MET3", 37: "PAD", 41: "POLY1TXT", 42: "MET1TXT", 44: "MET2TXT",
                  46: "MET3TXT", 47: "PADTXT", 48: "TEXT", 51: "RES", 52: "ESD", 53: "CAP", 54: "HVMS", 55: "HVMA",
                  56: "BJT", 57: "DIODE", 58: "NODRC", 59: "ESDD", 60: "LVSD"}
LAYERMAP_NAMES.update({100 + k: f"DUMMY{k}" for k in range(10)})   # the layer map as in the PDK (datatype 0)
LABEL_LAYERS = (41, 42, 44, 46, 47)
RESERVED = {1, 58} | set(range(100, 110))                      # KEY, NODRC, DUMMY0-9
GRID_NM = 10
DIE_UM = 1900.0
PREFIX = "pdkv_"
GPIO_IN_KIT = "pads_ETRI/GDS/ETRI_NSPL_GPIO_250610.gds"


def gpio_default():
    """The kit's GPIO library, the kit found as run_chip.sh finds it."""
    for kit in (os.environ.get("ETRI050_DK"), HERE.parents[2] / ".pdk/ETRI050_DesignKit", Path.home() / "ETRI050_DesignKit"):
        if kit and (Path(kit) / GPIO_IN_KIT).exists():
            return Path(kit) / GPIO_IN_KIT
    return None


def off_grid(points):
    return sum(1 for p in points if p.x % GRID_NM or p.y % GRID_NM)


def check(gds, gpio):
    ly = kdb.Layout()
    ly.read(str(gds))
    out, bad = [], False
    tops = ly.top_cells()
    top = tops[0]
    die = kdb.DBox(0, 0, DIE_UM, DIE_UM)
    bnd = kdb.Region(top.begin_shapes_rec(ly.layer(0, 0))).merged()
    ok = (len(tops) == 1 and top.name == "pdkv_Top" and abs(ly.dbu - 0.001) < 1e-12
          and bnd.count() == 1 and bnd.bbox().to_dtype(ly.dbu) == die and top.dbbox() == die)
    bad |= not ok
    out.append(f"file: top cells {[c.name for c in tops]}, dbu {ly.dbu * 1000:g} nm, extent {top.dbbox()}, "
               f"CHIPBOUNDARY {bnd.count()} shape(s) {bnd.bbox().to_dtype(ly.dbu)} -> {'ok' if ok else 'WRONG'}")

    used = {}
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        n = sum(1 for c in ly.each_cell() if not c.shapes(li).is_empty() for _ in c.shapes(li).each())
        if n:
            used[(info.layer, info.datatype)] = n
    foreign = [k for k in used if k[1] != 0 or k[0] not in LAYERMAP_NAMES]
    reserved = [LAYERMAP_NAMES[k[0]] for k in used if k[0] in RESERVED]
    bad |= bool(foreign) or bool(reserved)
    out.append("layers: " + ", ".join(f"{LAYERMAP_NAMES.get(l, '?')} {l}/{d} {n}" for (l, d), n in sorted(used.items()))
               + (f" -- not in the layer map: {foreign}" if foreign else " (all in the layer map)")
               + (f" -- not a designer's layer: {reserved}" if reserved else ""))

    # grid: shape vertices per layer (each cell once, in its own coordinates) and placements
    grid, tgrid = collections.Counter(), collections.Counter()
    for c in ly.each_cell():
        for li in ly.layer_indexes():
            for s in c.shapes(li).each():
                if s.is_text():
                    d = s.text.trans.disp
                    if d.x % GRID_NM or d.y % GRID_NM:
                        tgrid[(c.name, ly.get_info(li).layer)] += 1
                    continue
                if s.is_box():
                    b = s.box
                    pts = [b.p1, b.p2]
                elif s.is_path():
                    pts = list(s.path.each_point()) + [kdb.Point(s.path.width, 0)]
                else:
                    pts = list(s.polygon.each_point_hull()) + [p for h in range(s.polygon.holes())
                                                                 for p in s.polygon.each_point_hole(h)]
                k = off_grid(pts)
                if k:
                    grid[(c.name, ly.get_info(li).layer)] += k
        for inst in c.each_inst():
            if inst.cplx_trans.disp.x % GRID_NM or inst.cplx_trans.disp.y % GRID_NM:
                grid[(c.name, "placement")] += 1
    bad |= bool(grid)
    angle, paths, npath = collections.Counter(), [], 0
    for c in ly.each_cell():
        for li in ly.layer_indexes():
            for sh in c.shapes(li).each():
                if sh.is_text() or sh.is_box():
                    continue
                if sh.is_path():
                    npath += 1
                    pa = sh.path
                    if pa.width % (2 * GRID_NM) or pa.bgn_ext % GRID_NM or pa.end_ext % GRID_NM or pa.round:
                        paths.append(f"{c.name} layer {ly.get_info(li).layer}")
                for e in sh.polygon.each_edge():
                    if e.dx() and e.dy() and abs(e.dx()) != abs(e.dy()):
                        angle[(c.name, ly.get_info(li).layer)] += 1
    trans, pitch = [], []
    for c in ly.each_cell():
        for i in c.each_inst():
            t = i.cplx_trans
            if abs(t.mag - 1) > 1e-12 or not t.is_ortho() or t.is_mag():
                trans.append(f"{c.name}/{i.cell.name} {t}")
            if i.is_regular_array() and any(v % GRID_NM for v in (i.a.x, i.a.y, i.b.x, i.b.y)):
                pitch.append(f"{c.name}/{i.cell.name}")
    bad |= bool(angle) or bool(paths) or bool(trans) or bool(pitch)
    out.append("shapes: " + ("every edge orthogonal or 45 degrees" if not angle else "edges at other angles: " + ", ".join(
               f"{c} layer {l}: {k}" for (c, l), k in sorted(angle.items(), key=str)[:20]))
               + f"; paths {npath}" + (f", off the grid or round: {paths[:10]}" if paths else "")
               + "; placements: " + ("magnification 1, rotations by 90 degrees" if not trans else f"other: {trans[:10]}")
               + (", array pitches on the grid" if not pitch else f", array pitch off the grid: {pitch[:10]}"))
    out.append("grid 0.01 um: " + ("every vertex and placement on it" if not grid else
               "off grid: " + ", ".join(f"{c} layer {l}: {k}" for (c, l), k in sorted(grid.items(), key=str)[:30]))
               + "; text positions off it: " + (", ".join(f"{c} layer {l}: {k}" for (c, l), k in sorted(tgrid.items(), key=str))
                                                or "none"))

    arrays, degenerate = collections.Counter(), []
    for c in ly.each_cell():
        for i in c.each_inst():
            if i.is_regular_array():
                arrays[c.name] += 1
                if i.na * i.nb <= 1 or (i.na > 1 and i.a == kdb.Vector()) or (i.nb > 1 and i.b == kdb.Vector()):
                    degenerate.append(f"{c.name}/{i.cell.name}")
    bad |= bool(degenerate)
    out.append(f"arrays: {sum(arrays.values())} in " + ", ".join(f"{c} {k}" for c, k in sorted(arrays.items()))
               + (f" -- degenerate: {degenerate[:10]}" if degenerate else ", none degenerate"))

    # cells: ETRI GPIO library cells (same geometry) or ours
    lib = kdb.Layout()
    libnames = set()
    if gpio:
        lib.read(str(gpio))
        libnames = {c.name for c in lib.each_cell()}
    ours, gpio_cells, differ = [], [], []
    for c in ly.each_cell():
        if c.name in libnames:
            gpio_cells.append(c.name)
            if not same_cell(ly, c, lib, lib.cell(c.name)):
                differ.append(c.name)
        else:
            ours.append(c.name)
    bad |= bool(differ) or not gpio
    out.append(f"cells: {len(gpio_cells)} of ETRI's GPIO library" + (f" (geometry differs: {differ})" if differ else
               " with the library's geometry" if gpio else " (GPIO library not found: not compared)")
               + f"; {len(ours)} ours: " + ", ".join(f"{n}{'' if n.startswith(PREFIX) else ' (no prefix)'}" for n in sorted(ours)))

    texts = collections.Counter()
    labels = []
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        for s in top.shapes(li).each():
            if s.is_text():
                if info.layer in LABEL_LAYERS:
                    labels.append(f"{s.text.string}@{LAYERMAP_NAMES[info.layer]}")
                else:
                    texts[info.layer] += 1
    deep = collections.Counter()
    for c in ly.each_cell():
        if c.cell_index() == top.cell_index():
            continue
        for li in ly.layer_indexes():
            for s in c.shapes(li).each():
                if s.is_text():
                    deep[ly.get_info(li).layer] += 1
    bad |= bool(labels)
    out.append(f"labels: top cell on the LVS label layers: {len(labels)}" + (f" ({', '.join(labels[:40])})" if labels else "")
               + "; top cell on other layers: " + (", ".join(f"{LAYERMAP_NAMES.get(l, l)} {k}" for l, k in sorted(texts.items())) or "none")
               + "; inside cells (not read: TEXT DEPTH PRIMARY): " + ", ".join(f"{LAYERMAP_NAMES.get(l, l)} {k}" for l, k in sorted(deep.items())))
    out.append("chip GDS checks: " + ("PASS" if not bad else "FAIL"))
    return not bad, out


def same_cell(la, ca, lb, cb):
    """Same shapes on every layer, the hierarchy flattened (XOR empty)."""
    for li in la.layer_indexes():
        info = la.get_info(li)
        lj = lb.find_layer(info)
        ra = kdb.Region(ca.begin_shapes_rec(li))
        rb = kdb.Region(cb.begin_shapes_rec(lj)) if lj is not None else kdb.Region()
        if not (ra ^ rb).is_empty():
            return False
    for lj in lb.layer_indexes():
        if la.find_layer(lb.get_info(lj)) is None and not kdb.Region(cb.begin_shapes_rec(lj)).is_empty():
            return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    ap.add_argument("--gpio", type=Path, default=gpio_default())
    a = ap.parse_args(argv)
    ok, out = check(a.gds, a.gpio)
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
