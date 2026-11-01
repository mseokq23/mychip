"""Fill narrow notches inside metal2/metal3 polygons of a flat ETRI GDS.

The official rules 10.MET2.S1 and 12.MET3.S1 ask for 1.0 um space. The kit routing (3.0 um tracks,
2.1 um via pads) leaves 0.8-0.9 um notches inside one metal polygon where two via pads of the same
route are joined by a 1.05 um wire. A closing (grow, then shrink, by 0.49 um) fills every opening
narrower than 0.98 um. Filling a notch only adds metal to the polygon that already surrounds it, so
the script stops without writing the output if the closing would join two separate polygons: that
would be a gap between different shapes, not a notch, and filling it could connect different nets.

usage (KLayout batch mode):
  klayout -b -r scripts/fill_notches.py -rd infile=<flat.gds> -rd outfile=<filled.gds>
"""
import pya

LAYERS = ((34, 0, 'metal2'), (36, 0, 'metal3'))   # ETRI GDS numbers (kit Magic style lambda=0.30(ETRI))
HALF = 0.49                                        # um: fills openings narrower than 2 * HALF


def main(src, dst):
    ly = pya.Layout()
    ly.read(src)
    if len(ly.top_cells()) != 1:
        raise RuntimeError(f"{src}: expected one top cell (a flat GDS), found {len(ly.top_cells())}")
    top = ly.top_cell()
    h = int(round(HALF / ly.dbu))
    fills = []
    for layer, dtype, name in LAYERS:
        li = ly.find_layer(layer, dtype)
        if li is None:
            continue
        metal = pya.Region(top.begin_shapes_rec(li)).merged()
        closed = metal.sized(h).sized(-h).merged()
        if closed.count() != metal.count():
            raise RuntimeError(f"{name}: the closing joins separate polygons ({metal.count()} -> {closed.count()}); "
                               f"{dst} not written")
        added = closed - metal
        size = max([max(p.bbox().width(), p.bbox().height()) for p in added.each()] + [0]) * ly.dbu
        print(f"{name}: {metal.count()} polygons (unchanged), {added.count()} notches filled, "
              f"{added.area() * ly.dbu * ly.dbu:.1f} um2, largest piece {size:.2f} um")
        fills.append((li, added))
    for li, added in fills:
        top.shapes(li).insert(added)
    ly.write(dst)
    print(f"wrote {dst}")


main(globals().get('infile') or 'in.gds', globals().get('outfile') or 'out_fill.gds')
