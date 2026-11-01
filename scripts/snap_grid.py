"""Snap a flat ETRI GDS to the 0.01 um design grid.

The ETRI rule document (3.3 General Information) says "the design grid must be an integer multiple
of 0.01 um", and ETRI's Calibre deck flags off-grid vertices layer by layer (OFFGRID_MET2,
OFFGRID_CONT, ... in the kit's pong_pt1 MPW2025 report). The kit's KLayout deck has no grid check.

A block routed by the kit qflow flow is drawn in Magic quarter-lambda units (magscale 1 4, 0.075 um):
its metal2 wires are 1.05 um wide on whole-micron tracks, so their edges sit at x.475 / x.525 um, and a
few standard-cell contacts sit at x.775 / x.375 um. Every off-grid coordinate of such a layout is an odd
multiple of 0.005 um. The script moves each of them up by 0.005 um (round half up), on every layer:

  - the map is monotonic, so no two edges cross and the shapes keep their topology;
  - a distance between two edges changes only if exactly one of them was off the grid, by 0.005 um,
    and such a distance is itself an odd multiple of 0.005 um; a rule value (0.6, 0.8, 1.0, ...) is
    on the grid, so a distance that met a minimum rule before still meets it afterwards;
  - a cut whose size is exactly 0.6 or 0.8 um has both edges on the grid or both off it and keeps
    its size.

The script stops without writing if a coordinate is not a multiple of 0.005 um. It reports, per
layer, the off-grid coordinates before and after, the polygon count (merged) before and after, and
for each cut layer the cuts not covered by the layers it joins, before and after; all of these must
match for the output to be written.

usage (KLayout batch mode):
  klayout -b -r scripts/snap_grid.py -rd infile=<flat.gds> -rd outfile=<snapped.gds> [-rd grid=0.01]
"""
import pya

CUTS = ((31, (32,), 'CONT in MET1'), (33, (32, 34), 'VIA1 in MET1 and MET2'),
        (35, (34, 36), 'VIA2 in MET2 and MET3'))


def main(src, dst, grid_um):
    ly = pya.Layout()
    ly.read(src)
    if len(ly.top_cells()) != 1:
        raise RuntimeError(f"{src}: expected one top cell (a flat GDS), found {len(ly.top_cells())}")
    top = ly.top_cell()
    g = int(round(grid_um / ly.dbu))
    half = g // 2
    if g % 2 or abs(g * ly.dbu - grid_um) > 1e-9:
        raise RuntimeError(f"grid {grid_um} um is not an even number of database units ({ly.dbu} um)")

    def snap(v):
        r = v % g
        if r == 0:
            return v
        if r != half:
            raise RuntimeError(f"coordinate {v * ly.dbu:.4f} um is not a multiple of {half * ly.dbu} um; "
                               f"{dst} not written")
        return v + half

    def off(region):
        return sum((p.x % g != 0) + (p.y % g != 0) for poly in region.each() for p in poly.each_point_hull()) + \
            sum((p.x % g != 0) + (p.y % g != 0) for poly in region.each() for h in range(poly.holes())
                for p in poly.each_point_hole(h))

    before, after = {}, {}
    for li in ly.layer_indexes():
        if top.bbox_per_layer(li).empty():
            continue
        reg = pya.Region(top.begin_shapes_rec(li)).merged()
        out = pya.Region()
        for poly in reg.each():
            p2 = pya.Polygon([pya.Point(snap(p.x), snap(p.y)) for p in poly.each_point_hull()])
            for h in range(poly.holes()):
                p2.insert_hole([pya.Point(snap(p.x), snap(p.y)) for p in poly.each_point_hole(h)])
            out.insert(p2)
        before[li], after[li] = reg, out.merged()

    bad = 0
    for li in before:
        info = ly.get_info(li)
        n0, n1 = before[li].count(), after[li].count()
        o0, o1 = off(before[li]), off(after[li])
        bad += (n0 != n1) + (o1 != 0)
        print(f"layer {info.layer}/{info.datatype}: polygons {n0} -> {n1}, off-grid coordinates {o0} -> {o1}")
    find = lambda regs, n: next((regs[li] for li in regs if ly.get_info(li).layer == n
                                 and ly.get_info(li).datatype == 0), pya.Region())
    for cut, metals, name in CUTS:
        for regs, tag in ((before, 'before'), (after, 'after')):
            c = find(regs, cut)
            loose = c.not_inside(find(regs, metals[0]))
            for m in metals[1:]:
                loose = loose + c.not_inside(find(regs, m))
            if tag == 'before':
                n0 = loose.count()
            else:
                n1 = loose.count()
        bad += (n0 != n1)
        print(f"{name}: cuts not inside {n0} -> {n1}")
    if bad:
        raise RuntimeError(f"{bad} check(s) changed by snapping; {dst} not written")
    for li in before:
        top.shapes(li).clear()
        top.shapes(li).insert(after[li])
    ly.write(dst)
    print(f"wrote {dst} (grid {grid_um} um)")


main(globals().get('infile') or 'in.gds', globals().get('outfile') or 'out_grid.gds',
     float(globals().get('grid') or 0.01))
