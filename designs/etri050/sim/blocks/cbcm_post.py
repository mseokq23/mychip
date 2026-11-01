"""CBCM block after layout: the block netlist with the wiring capacitance of the drawn block.

cbcm_block.py ran the block's schematic netlist with the planned structure values. This adds what the
drawing adds, from designs/etri050/cbcm/cbcm_c.py (rule document v1.1 table on the drawn GDS; run it
first, it writes designs/etri050/cbcm/build/cbcm_c.json):
  nodes      ND<i>, NR<i>: wiring capacitance (metal, field poly) to held nets as a capacitor to ground,
             to the nets that switch (NG, PG<i>, PCK, the generator, the other cells' nodes) as coupling
             capacitors
  switching  the generator's nodes, PCK, NG, PG<i>: the rest of their wiring load, to ground
  structures drawn geometry with the PDK models: PIP pipcap_i (COX x area + CAPSW x perimeter, linear),
             N+ ndiode (area, perimeter not facing a gate), gates nmos4 (W / L as drawn = as netlisted);
             the metal structures are part of their node's wiring capacitance
Junction and gate capacitance of the devices stay in their models (simlib.geo for the pairs, AD/AS/PD/PS
in the kit's cell netlists), so the wiring terms leave them out.

Expected reading of cell i = Q(V)/V of its structure model + wiring(ND<i>) - wiring(NR<i>) (the lead;
the pairs are drawn alike, cbcm_c.py). The checks are those of cbcm_block.py on this netlist, and the
C-V of the N+ and gate cells (6-9) at VCD 1.5-5 V, which the measurement plan compares with.
"""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import json
import os
import re

import cbcm_block as pre
from cbcm_block import gen
from simlib import run

CJSON = os.path.join(str(gen.DEFAULT_OUT), 'cbcm_c.json')
COX, CAPSW = 5.0e-4, 9.0e-11            # pipcap_i (05cmos_model_260210.lib, .LIB CAP)
VOLTS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
CV_CELLS = (6, 7, 8, 9)
MODEL_CELLS = (1, 6, 7, 8, 9)           # the metal structures (2-5) are wiring: no device model
NODES = [f"N{t}{i}" for i in range(gen.NCELL) for t in "DR"]


def junction_params(name):
    """CJ, PB, MJ, CJSW, sidewall PB, MJSW of the PDK's n+ junction descriptions: the ndiode device
    (05cmos_model_260210.lib) and the nmos4 source / drain (05cmos_mosfet_corner.lib), as simulated."""
    path = '05cmos_model_260210.lib' if name == 'ndiode' else '05cmos_mosfet_corner.lib'
    txt = open(os.path.join(pre.BUILD, path)).read()
    body = re.search(rf'\.MODEL\s+{name}\b(.*?)\)', txt, re.S | re.I).group(1)
    p = {k.upper(): float(v) for k, v in re.findall(r'(\w+)\s*=\s*([-+0-9.Ee]+)', body)}
    return p['CJ'], p['PB'], p['MJ'], p['CJSW'], p['PHP' if name == 'ndiode' else 'PBSW'], p['MJSW']


def junction_qv(name, area_um2, perim_um, v):
    """Q(V)/V of an n+ junction charged from 0 to v (reverse), from the model's depletion capacitance."""
    cj, pb, mj, cjsw, pbsw, mjsw = junction_params(name)
    f = lambda c, b, m: c * b / ((1 - m) * v) * ((1 + v / b) ** (1 - m) - 1)
    return f(cj, pb, mj) * area_um2 * 1e-12 + f(cjsw, pbsw, mjsw) * perim_um * 1e-6


def wiring(keys):
    return sum(v[2] for k, v in keys.items() if k.split('/')[0] in ('m1', 'm2', 'm3') or k.startswith('poly/field'))


def drawn():
    """Structure values (ideal, diode) from the drawn geometry, and per-cell wiring difference (fF)."""
    c = json.load(open(CJSON))
    g = {int(k): v for k, v in c['drawn'].items()}
    ideal = {1: COX * g[1]['area_um2'] * 1e-12 + CAPSW * g[1]['edge_um'] * 1e-6}
    diode = {i: (g[i]['area_um2'] * 1e-12, g[i]['edge_um'] * 1e-6) for i in (6, 7)}
    lead = {}
    for i in range(gen.NCELL):
        w = {n: sum(wiring(ks) for ks in c['couplings'][n].values()) for n in (f"ND{i}", f"NR{i}")}
        lead[i] = (w[f"ND{i}"] - w[f"NR{i}"]) * 1e-15
    return ideal, diode, lead, g


def node(net):
    """Netlist node of a block net: the block's ports are the test bench's nodes, the rest xb.<net>."""
    ports = {"clk": "clk", "VCD": "vcd", "VCR": "vcr", "VDD": "vdd", "VSS": "0"}
    ports.update({f"en{i}": f"en{i}" for i in range(gen.NCELL)})
    return ports.get(net, f"xb.{net}")


def parasitics():
    """Capacitor lines on the instance's nodes (xb.<net>) from cbcm_c.json."""
    c = json.load(open(CJSON))['couplings']
    ground, pairs = defaultdict(float), {}
    for n in NODES:
        for other, ks in c[n].items():
            w = wiring(ks)
            if w <= 0:
                continue
            if other in c:                      # a node or a switching net: keep it as a coupling capacitor
                key = tuple(sorted((n, other)))
                pairs[key] = max(pairs.get(key, 0.0), w)
            else:
                ground[n] += w
    for s in [k for k in c if k not in NODES and not k.endswith(('_facing_um', '_body'))]:
        tot = sum(wiring(ks) for ks in c[s].values())
        to_nodes = sum(w for (a, b), w in pairs.items() if s in (a, b))
        ground[s] += max(tot - to_nodes, 0.0)
    lines = [f"cw{k} {node(n)} 0 {v:.4f}f" for k, (n, v) in enumerate(sorted(ground.items())) if v > 0]
    lines += [f"cc{k} {node(a)} {node(b)} {v:.4f}f" for k, ((a, b), v) in enumerate(sorted(pairs.items()))]
    return "* wiring capacitance of the drawn block (cbcm_c.py)\n" + "\n".join(lines) + "\n"


def job(args):
    kind, sel, kw = args
    ideal, diode, _, _ = drawn()
    if kind == 'truth':
        return run(pre.truth_netlist(sel, kw['v'], ideal=ideal, diode=diode),
                   f"cbcmp_true_{sel}_{kw['v']}".replace('.', 'p')).get('c', float('nan'))
    tag = 'cbcmp_' + '_'.join(f"{k}{v}" for k, v in sorted(kw.items()) if k != 'cells') + f"_s{sel}"
    if 'cells' in kw:
        tag += '_c' + ''.join(map(str, kw['cells']))
    tag = tag.replace(' ', '').replace('.', 'p')
    r = run(pre.netlist(sel, ideal=ideal, diode=diode, extra=parasitics(), **kw), tag)
    log = open(os.path.join(pre.BUILD, tag + '.log')).read()
    if 'Timestep too small' in log or 'out of interval' in log.split('RES')[0]:
        r = {k: float('nan') for k in ('c', 'id', 'ir', 'gap_on', 'gap_off')}
    return r


def main():
    ideal, diode, lead, g = drawn()
    jobs = {}
    for i in range(gen.NCELL):
        jobs[('acc', i)] = ('meas', i, {})
        if i in MODEL_CELLS:
            jobs[('true', i)] = ('truth', i, {'v': 5.0})
    for corner in ('SS', 'FF', 'SF', 'FS'):
        jobs[('corner', corner, 27)] = ('meas', 2, dict(corner=corner))
    for corner in ('TT', 'SS', 'FF'):
        jobs[('corner', corner, 125)] = ('meas', 2, dict(corner=corner, temp=125))
        for vdd in (4.5, 5.5):
            jobs[('vdd', corner, vdd)] = ('meas', 2, dict(corner=corner, vdd=vdd))
    for f in (0.2e6, 5e6):
        jobs[('freq', f)] = ('meas', 2, dict(f=f))
    jobs[('idle',)] = ('meas', None, dict(clock=False))
    for i in (2, 8):
        jobs[('pad', i)] = ('meas', i, dict(rpad=725.0))
    for i in CV_CELLS:
        for v in VOLTS:
            jobs[('cv', i, v)] = ('meas', i, dict(vddm=v))
            jobs[('cvtrue', i, v)] = ('truth', i, {'v': v})
    keys = list(jobs)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        vals = dict(zip(keys, ex.map(job, [jobs[k] for k in keys])))

    out = {}
    print("drawn structures: " + "; ".join(f"{i} {v['what']} {v['area_um2']:.2f} um2 / {v['edge_um']:.2f} um"
                                         for i, v in sorted(g.items())))
    print(f"{'cell':4s} {'structure':16s} {'model fF':>9s} {'lead fF':>8s} {'expect fF':>9s} {'CBCM fF':>9s} "
          f"{'err fF':>7s} {'err %':>7s} {'- cell 0':>9s}")
    c0 = vals[('acc', 0)].get('c', float('nan'))
    for i in range(gen.NCELL):
        c = vals[('acc', i)].get('c', float('nan'))
        t = vals.get(('true', i), 0.0)
        e = t + lead[i]
        out[('acc', i)] = (c, e)
        pct = f"{100 * (c / e - 1):+7.2f}" if e > 1e-15 else '      -'
        print(f"{i:4d} {gen.STRUCTURES[i]:16s} {t * 1e15:9.2f} {lead[i] * 1e15:8.2f} {e * 1e15:9.2f} {c * 1e15:9.2f} "
              f"{(c - e) * 1e15:+7.2f} {pct} {(c - c0) * 1e15:9.2f}")
    gaps = []
    for k in [('acc', 2)] + [k for k in keys if k[0] in ('corner', 'vdd', 'freq')]:
        r = vals[k]
        gaps.append((k, r.get('gap_on', float('nan')), r.get('gap_off', float('nan')), r.get('c', float('nan'))))
    print("non-overlap at the cell 2 gates (NG at VTN, PG at VCD - VTP) and cell 2 error:")
    e2 = out[('acc', 2)][1]
    for k, on, off, c in gaps:
        print(f"  {str(k):28s} NMOS off -> PMOS on {on * 1e9:6.2f} ns, PMOS off -> NMOS on {off * 1e9:6.2f} ns,"
              f" C err {100 * (c / e2 - 1):+.2f} %")
    out['gap_min'] = min(min(on, off) for _, on, off, _ in gaps)
    out['err2_span'] = max(100 * (c / e2 - 1) for *_, c in gaps) - min(100 * (c / e2 - 1) for *_, c in gaps)
    r = vals[('idle',)]
    out['idle'] = (r.get('id', float('nan')), r.get('ir', float('nan')))
    print(f"idle (no clock, no cell): I(VCD) {-out['idle'][0] * 1e12:.3f} pA, I(VCR) {-out['idle'][1] * 1e12:.3f} pA")
    for i in (2, 8):
        p = vals[('pad', i)]['c']
        out[('pad', i)] = 100 * (p - out[('acc', i)][0]) / out[('acc', i)][1]
        print(f"PADR 725 ohm, cell {i}: change {out[('pad', i)]:+.3f} %p")
    out['cv'] = {}
    for i in CV_CELLS:
        rows = []
        for v in VOLTS:
            c, t = vals[('cv', i, v)].get('c', float('nan')), vals[('cvtrue', i, v)]
            rows.append((v, c, t + lead[i]))
        out['cv'][i] = rows
        print(f"C-V cell {i} ({gen.STRUCTURES[i]}), expected (model + lead) / CBCM fF: " +
              ", ".join(f"{v:.1f} V {e * 1e15:.1f}/{c * 1e15:.1f}" for v, c, e in rows))
    # the PDK describes the n+ junction twice, and the two disagree on the sidewall (CJSW): cells 6
    # (area) and 7 (edge) tell which one the silicon follows
    out['junction'] = {}
    for i in (6, 7):
        a, p = g[i]['area_um2'], g[i]['edge_um']
        for v in (1.5, 3.0, 5.0):
            nd, nm = junction_qv('ndiode', a, p, v), junction_qv('nmos4', a, p, v)
            out['junction'][(i, v)] = (nd, nm)
        print(f"cell {i} junction Q(V)/V (fF, without lead) ndiode / nmos4 source-drain: " +
              ", ".join(f"{v:.1f} V {out['junction'][(i, v)][0] * 1e15:.1f} / {out['junction'][(i, v)][1] * 1e15:.1f}"
                        for v in (1.5, 3.0, 5.0)))
    return out


if __name__ == '__main__':
    main()
