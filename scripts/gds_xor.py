"""Compare two GDS files layer by layer, flattened: area of the XOR per layer (KLayout batch mode).

Timestamps make two GDS files of the same layout differ byte by byte, so a layout is compared by
its geometry. Each file must have one top cell; the cell names may differ.

usage: klayout -b -r scripts/gds_xor.py -rd a=<first.gds> -rd b=<second.gds>
"""
import pya


def regions(path):
    ly = pya.Layout()
    ly.read(path)
    if len(ly.top_cells()) != 1:
        raise RuntimeError(f'{path}: {len(ly.top_cells())} top cells')
    top = ly.top_cell()
    out = {}
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        reg = pya.Region(top.begin_shapes_rec(li)).merged()
        if not reg.is_empty():
            out[(info.layer, info.datatype)] = (reg, ly.dbu)
    return out


a, b = regions(globals()['a']), regions(globals()['b'])
diff = 0
for key in sorted(set(a) | set(b)):
    ra, dbu = a.get(key, (pya.Region(), 0.001))
    rb, _ = b.get(key, (pya.Region(), 0.001))
    x = ra ^ rb
    area = x.area() * dbu * dbu
    diff += area > 0
    print(f'layer {key[0]}/{key[1]}: {ra.count()} vs {rb.count()} polygons, XOR {area:.4f} um2')
print('identical geometry' if diff == 0 else f'{diff} layer(s) differ')
