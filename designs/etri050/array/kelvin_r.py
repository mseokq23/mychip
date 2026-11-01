#!/usr/bin/env python3
"""Resistances inside the Kelvin loops of the array, extracted from its drawn layout.

Each cell is measured with four Kelvin terminals, but two short paths stay between a sense point and
the device:
  source: the source contacts -> MET1 strip -> VIA1 column -> MET2 -> VIA2 column -> MET3 plate. ASS
          senses the plate at its centre and ASF forces it at its left edge, so the measurement sees
          V(source) - V(ASS) = I * (r_s_cont + r_s_metal) for the selected cell.
  drain:  the force current enters the drain contact strip (MET1) at its top end and the cell TG
          senses the strip's bottom end, so the sense reads I * r_d_metal off the strip potential
          at the contacts (r_d_metal < 0: below), plus the drain contacts r_d_cont.
The contacts belong to the device as drawn (the L-split cells have the same contact strips); the
metal and via parts (r_s_metal + r_d_metal) are the array's path error, which the plan's array
simulations did not have (their source tap carried no current).

Extraction: KLayout's R extractor (klayout.pex, KLayout >= 0.30.2) on the SRC net and on each D<c>
net of the GDS, with the rule document's sheet resistances (5.2: MET1/MET2 0.08, MET3 0.05 ohm/sq
typ; 0.10/0.10/0.06 max) and contact/via resistances (5.3: N+ 30, P+ 90, VIA1 2.0, VIA2 1.5
ohm/ea typ; 50/110/3.0/2.5 max). The source contacts are ports, each through its contact resistance
to one source node per cell; the plate's ASF entry is where the chip's 9 um MET3 strip meets the
plate edge (taken from the chip build, or --asf-y).

Writes build/kelvin_r.json and build/kelvin_r.csv (one row per cell and corner, ohm) and prints a
summary. usage: python3 designs/etri050/array/kelvin_r.py [--gds build/karray.gds] [--asf-y UM]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import klayout.db as db
import klayout.pex as pex

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "designs/etri050/gen"))
import etri050_array as A  # noqa: E402

LAM = 0.3
CORNERS = {'typ': dict(m1=0.08, m2=0.08, m3=0.05, v1=2.0, v2=1.5, nc=30.0, pc=90.0),
           'max': dict(m1=0.10, m2=0.10, m3=0.06, v1=3.0, v2=2.5, nc=50.0, pc=110.0)}
CUT_AREA = 0.64           # um2: VIA1/VIA2 are 0.8 x 0.8 um


def tech_stack(v, layers):
    tech = pex.RExtractorTech()
    for lid, key in layers:
        c = pex.RExtractorTechConductor()
        c.layer, c.resistance = lid, v[key]
        if key == 'm3':                       # the plate: 2-D spreading
            c.algorithm = pex.Algorithm.Tesselation
            c.triangulation_max_area = 20.0
            c.triangulation_min_b = 1.0
        tech.add_conductor(c)
    for cut, lo, hi, key in ((11, 1, 2, 'v1'), (12, 2, 3, 'v2')):
        if any(lid == hi for lid, _ in layers):
            t = pex.RExtractorTechVia()
            t.cut_layer, t.bottom_conductor, t.top_conductor = cut, lo, hi
            t.resistance = v[key] * CUT_AREA
            tech.add_via(t)
    return tech


class Nodal:
    """Nodal analysis of an extracted network plus extra resistors to added nodes."""

    def __init__(self, net, extra_nodes):
        self.idx, self.vport, self.pport = {}, {}, {}
        for nd in net.each_node():
            self.idx[nd.object_id()] = len(self.idx)
            if nd.type() == pex.RNode.PolygonPort:
                self.pport[(nd.layer(), nd.port_index())] = self.idx[nd.object_id()]
            elif nd.type() == pex.RNode.VertexPort:
                self.vport[(nd.layer(), nd.port_index())] = self.idx[nd.object_id()]
        self.base = len(self.idx)
        self.G = np.zeros((self.base + extra_nodes,) * 2)
        for e in net.each_element():
            self.add(self.idx[e.a().object_id()], self.idx[e.b().object_id()], e.resistance())

    def add(self, a, b, r):
        g = 1.0 / max(r, 1e-9)
        self.G[a, a] += g
        self.G[b, b] += g
        self.G[a, b] -= g
        self.G[b, a] -= g

    def solve(self, gnd, inject):
        keep = [k for k in range(len(self.G)) if k != gnd]
        pos = {k: j for j, k in enumerate(keep)}
        cur = np.zeros(len(keep))
        cur[pos[inject]] = 1.0
        v = np.linalg.solve(self.G[np.ix_(keep, keep)], cur)
        return lambda k: 0.0 if k == gnd else v[pos[k]]


def metal_nets(ly, top, names):
    num = {'m1': 32, 'v1': 33, 'm2': 34, 'v2': 35, 'm3': 36}
    l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(ly, top, []))
    reg = {n: l2n.make_layer(ly.find_layer(num[n], 0), n) for n in names}
    for a, b in zip(names, names[1:]):
        l2n.connect(reg[a])
        l2n.connect(reg[a], reg[b])
    l2n.connect(reg[names[-1]])
    l2n.extract_netlist()
    return l2n, reg


def cell_frame(r, cx):
    pmos = A.row_pmos(r)
    a = (A.row_y(r) + (A.A_P if pmos else A.A_N)) * LAM      # device active bottom (um)
    return pmos, a


def source_side(ly, top, pins, asf_y):
    l2n, reg = metal_nets(ly, top, ['m1', 'v1', 'm2', 'v2', 'm3'])
    x0, y0, x1, y1 = pins['SRC_EDGE']['box']
    src = l2n.probe_net(reg['m3'], db.DPoint((x0 + x1) / 2, asf_y))
    geo = {k: l2n.shapes_of_net(src, reg[k], True).merged() for k in reg}
    cont = db.Region(top.begin_shapes_rec(ly.find_layer(31, 0)))
    um = lambda v: int(round(v / ly.dbu))
    cells, ports = [], []
    for cx in A.columns():
        g = A.col_geom(cx.c)
        if g is None:
            continue
        w, l = g
        for r in range(A.NROWS):
            pmos, a = cell_frame(r, cx)
            sbox = db.DBox(cx.da * LAM, a, (cx.da + A.CT) * LAM, a + w * LAM).to_itype(ly.dbu)
            cs = list((cont & geo['m1'] & db.Region(sbox)).each())
            if len(cs) < 1:
                raise RuntimeError(f'cell {r},{cx.c}: no source contacts found')
            cells.append(dict(row=r, col=cx.c, pmos=pmos, w=w * LAM, l=l * LAM, n_s=len(cs)))
            ports += [(len(cells) - 1, p) for p in cs]
    ax0, ay0, ax1, ay1 = pins['ASS']['box']
    ass = db.Point(um((ax0 + ax1) / 2), um((ay0 + ay1) / 2))
    asf = db.Polygon(db.DBox(x0, asf_y - 4.5, x1, asf_y + 4.5).to_itype(ly.dbu))
    out = {}
    for corner, v in CORNERS.items():
        net = pex.RNetExtractor(ly.dbu).extract(
            tech_stack(v, ((1, 'm1'), (2, 'm2'), (3, 'm3'))),
            {1: geo['m1'], 2: geo['m2'], 3: geo['m3'], 11: geo['v1'], 12: geo['v2']},
            {3: [ass]}, {1: [p for _, p in ports], 3: [asf]})
        nd = Nodal(net, len(cells))
        for k, (ci, _) in enumerate(ports):
            nd.add(nd.pport[(1, k)], nd.base + ci, v['pc'] if cells[ci]['pmos'] else v['nc'])
        for ci, cell in enumerate(cells):
            V = nd.solve(nd.pport[(3, 0)], nd.base + ci)
            vs = V(nd.vport[(3, 0)])
            vm = np.mean([V(nd.pport[(1, k)]) for k, (o, _) in enumerate(ports) if o == ci])
            out[(corner, cell['row'], cell['col'])] = dict(cell, r_s_metal=vm - vs, r_s_cont=V(nd.base + ci) - vm)
    return out


def drain_side(ly, top, cells):
    l2n, reg = metal_nets(ly, top, ['m1', 'v1', 'm2'])
    cont = db.Region(top.begin_shapes_rec(ly.find_layer(31, 0)))
    um = lambda v: int(round(v / ly.dbu))
    out = {}
    for cx in A.columns():
        g = A.col_geom(cx.c)
        if g is None:
            continue
        w, _ = g
        xd = (cx.dc[0] + cx.dc[1]) / 2 * LAM
        dnet = l2n.probe_net(reg['m2'], db.DPoint(xd, -1.0))     # D<c> just under row 0
        geo = {k: l2n.shapes_of_net(dnet, reg[k], True).merged() for k in reg}
        for r in range(A.NROWS):
            pmos, a = cell_frame(r, cx)
            dbox = db.DBox(cx.d_tile * LAM, a, (cx.d_tile + A.CT) * LAM, a + w * LAM).to_itype(ly.dbu)
            tbox = db.DBox(cx.tn * LAM, a, (cx.tn + A.CT) * LAM, a + 4 * LAM).to_itype(ly.dbu)
            dcs = list((cont & geo['m1'] & db.Region(dbox)).each())
            tcs = list((cont & geo['m1'] & db.Region(tbox)).each())
            if not dcs or not tcs:
                raise RuntimeError(f'cell {r},{cx.c}: {len(dcs)} drain / {len(tcs)} TG contacts found')
            for corner, v in CORNERS.items():
                net = pex.RNetExtractor(ly.dbu).extract(
                    tech_stack(v, ((1, 'm1'), (2, 'm2'))), {1: geo['m1'], 2: geo['m2'], 11: geo['v1']},
                    {2: [db.Point(um(xd), um(-1.0))]}, {1: dcs + tcs})
                nd = Nodal(net, 1)
                for k in range(len(dcs)):
                    nd.add(nd.pport[(1, k)], nd.base, v['pc'] if pmos else v['nc'])
                V = nd.solve(nd.base, nd.vport[(2, 0)])
                vm = np.mean([V(nd.pport[(1, k)]) for k in range(len(dcs))])
                vs = np.mean([V(nd.pport[(1, len(dcs) + k)]) for k in range(len(tcs))])
                cells[(corner, r, cx.c)].update(n_d=len(dcs), r_d_metal=vs - vm, r_d_cont=vm)
    return cells


def asf_from_chip(default):
    spec = REPO / "designs/etri050/chip/build/pdkv_nets.json"
    if spec.exists():
        s = json.loads(spec.read_text())
        blk = next((b for b in s['blocks'] if b['name'] == 'karray'), None)
        asf = next((p for p in s['nets'].get('SRC', []) if p['at'].endswith(':ASF')), None)
        if blk and asf:
            return round(asf['y'] - blk['y'], 3), 'chip build'
    return default, 'default'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--gds', default=str(A.DEFAULT_OUT / 'karray.gds'))
    ap.add_argument('--asf-y', type=float, default=None,
                    help='y of the ASF strip centre at the plate edge, array coordinates (um)')
    args = ap.parse_args()
    gds = Path(args.gds)
    pins = json.loads((gds.parent / 'karray_pins.json').read_text())['pins']
    asf_y, how = (args.asf_y, 'given') if args.asf_y is not None else asf_from_chip(117.6)
    ly = db.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    ly.flatten(top.cell_index(), -1, True)
    cells = drain_side(ly, top, source_side(ly, top, pins, asf_y))
    rows = []
    for (corner, r, c), x in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
        rows.append(dict(corner=corner, row=r, col=c, type='pmos' if x['pmos'] else 'nmos', w=x['w'], l=x['l'],
                         n_s=x['n_s'], n_d=x['n_d'], r_s_metal=round(x['r_s_metal'], 4),
                         r_d_metal=round(x['r_d_metal'], 4), r_path=round(x['r_s_metal'] + x['r_d_metal'], 4),
                         r_s_cont=round(x['r_s_cont'], 3), r_d_cont=round(x['r_d_cont'], 3)))
    out = gds.parent
    (out / 'kelvin_r.json').write_text(json.dumps(dict(gds=gds.name, asf_y=asf_y, cells=rows), indent=1))
    with open(out / 'kelvin_r.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"ASF entry y {asf_y} um ({how}); per-cell Kelvin path resistances (ohm), metal+via = source + drain:")
    for corner in CORNERS:
        for c in range(A.NCOLS):
            sel = [x for x in rows if x['corner'] == corner and x['col'] == c]
            if not sel:
                continue
            for t in ('nmos', 'pmos'):
                s = [x for x in sel if x['type'] == t]
                rng = lambda k: f"{min(x[k] for x in s):.3f}..{max(x[k] for x in s):.3f}"
                print(f"  {corner} col {c} W/L {s[0]['w']:g}/{s[0]['l']:g} {t}: source {rng('r_s_metal')}, drain "
                      f"{rng('r_d_metal')}, path {rng('r_path')}; contacts S {s[0]['r_s_cont']:.1f} "
                      f"({s[0]['n_s']}) D {s[0]['r_d_cont']:.1f} ({s[0]['n_d']})")
    print(f"wrote {out / 'kelvin_r.json'} and kelvin_r.csv")


if __name__ == '__main__':
    main()
