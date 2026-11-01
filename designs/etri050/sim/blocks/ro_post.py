"""RO bank as drawn (designs/etri050/gen/etri050_ro.py): the block's own netlist, before and after layout.

ro_bank.py checked the plan's ROs with 5 fF of wiring per node (and 43.5 fF for the wire RO's 300 um
of MET1). This runs the ROs of the drawn block, with their tap INVX1 -> INVX4 on stage 0's output:
  plan      the block netlist with the plan's loads (5 fF per node, wire RO + 43.5 fF): differs from
            ro_bank.py only by the tap's input on stage 0's output
  layout    the block netlist with each node's wiring capacitance from the drawn GDS (metal and field
            poly, rule document v1.1 table, designs/etri050/cbcm/cbcm_c.py's extractor; junctions and
            gates stay in the device models). Every node's coupling is put to ground: the table has no
            value for neighbours on one layer (the wire RO's legs 2.1 um apart), see the README
Frequency from rise 6 to 16 of stage 5, as ro_bank.py; 5 corners at 27 C and TT at 125 C.

The resistor RO (block rores, index 5) the same way, from rores_full.gds:
  plan      5 fF on every stage node after the resistor, the resistor a plain p2res 40 squares (no
            contacts), as ro_bank.py, plus the tap
  layout    each node's wiring from the GDS without its POLY2 (so the two heads of a resistor stay two
            nets), and every resistor as the drawn body: p2res RSH x squares (LVSD length / width, PDK
            TC1 / TC2), one POLY2 contact at each end (rule document 5.3: 50 ohm typical), the body's
            capacitance spread over NSEG segments. The capacitance table (5.5) has no POLY2-to-field row;
            POLY1's "Poly to field" stands in (POLY2 lies higher, so the value is an upper bound) and the
            run without any body capacitance brackets it. Sheet resistance 110 / 140 ohm/sq (5.2 min /
            max) at TT for the resistor's own spread.

usage: python3 ro_post.py   (needs designs/etri050/ro/build/robank_flat.gds and, for the resistor RO,
                             rores_full.gds: run etri050_ro.py first)
"""
from concurrent.futures import ProcessPoolExecutor
import os
import sys

from simlib import header, p2res, run

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'gen'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'cbcm'))
import etri050_ro as gen  # noqa: E402

GDS = os.path.join(str(gen.DEFAULT_OUT), 'robank_flat.gds')
PLAN = {'inv': 123.1, 'nand': 93.8, 'nor': 66.8, 'wire': 65.0}     # ro_bank.py, TT 27 C, MHz
CORNERS = ['TT', 'SS', 'FF', 'SF', 'FS']
_LOADS = None


def wiring_loads():
    """{net: fF} of every RO node: wiring capacitance of the drawn block (cached per process)."""
    global _LOADS
    if _LOADS is None:
        import cbcm_c
        blk, _ = gen.build()
        ex = cbcm_c.Extract(GDS, blk=blk, critical=lambda n: n[:1] in "rti" and n[1:2].isdigit())
        _LOADS = {}
        for i in gen.KINDS:
            for net in [f"r{i}_{s}" for s in range(gen.NST)] + [f"t{i}", f"in{i}"]:
                _LOADS[net] = sum(cbcm_c.wiring(ks) for ks in cbcm_c.flat(ex.couplings(net)).values())
    return _LOADS


def ro_netlist(i, kind, loads, corner, temp, vdd=5.0):
    order = {"INVX1": "A Y", "INVX4": "A Y", "NAND2X1": "A B Y", "NOR2X1": "A B Y"}
    n = header(corner, temp) + f"vdd vdd 0 {vdd}\nven en{i} 0 pwl(0 0 20n 0 20.5n {vdd})\n"
    for inst, cell, pins in gen.stage_nets(i, kind):
        nodes = [{"VDD": "vdd", "VSS": "0"}.get(pins[p], pins[p]) for p in order[cell].split()]
        n += f"{inst} {' '.join(nodes)} vdd 0 {cell}\n"
    for net, c in loads.items():
        if c > 0:
            n += f"c_{net} {net} 0 {c:.3f}f\n"
    tstop = 900e-9 if kind in ('wire', 'nor') else 400e-9
    n += f""".control
set noaskquit
tran 0.05n {tstop}
meas tran t1 when v(r{i}_5)={vdd / 2} rise=6
meas tran t2 when v(r{i}_5)={vdd / 2} rise=16
let f = 10 / (t2 - t1)
meas tran iavg avg i(vdd) from=t1 to=t2
let p = -iavg * {vdd}
echo "RES f=$&f p=$&p"
quit
.endc
.end
"""
    return n


def plan_loads(i, kind):
    out = {f"r{i}_{s}": 5.0 + (43.5 if kind == 'wire' else 0.0) for s in range(gen.NST)}
    return out


def job(args):
    which, i, kind, corner, temp = args
    if which == 'plan':
        loads = plan_loads(i, kind)
    else:
        loads = {k: v for k, v in wiring_loads().items() if k.startswith((f"r{i}_", f"t{i}", f"in{i}"))}
    r = run(ro_netlist(i, kind, loads, corner, temp), f"rob_{which}_{kind}_{corner}_{temp}")
    return r.get('f', float('nan')), r.get('p', float('nan'))


# ---- resistor RO -------------------------------------------------------------------------------------
RES_GDS = os.path.join(str(gen.DEFAULT_OUT), 'rores_full.gds')
PLAN_RES = 69.1                       # ro_bank.py res, TT 27 C, MHz
RCONT = 50.0                          # rule document 5.3, POLY2 contact 0.6 um, typical, ohm per contact
NSEG = 10                             # RC segments per resistor body
POLY_FIELD = (0.0902, 0.0519)         # rule document 5.5 "Poly to field" (fF/um2, fF/um), for POLY2 (no row)
_RLOADS = None


def res_geometry():
    """(squares, POLY2 area um2, POLY2 perimeter um) of one drawn resistor (etri050_ro.p2r_um)."""
    a, b, c, d = gen.p2r_um()['POLY2'][0]
    _, lb, _, ld = gen.p2r_um()['LVSD'][0]
    w, h = c - a, d - b
    return (ld - lb) / w, w * h, 2 * (w + h)


def res_wiring_loads():
    """{net: fF} of the resistor RO's nodes: rores_full.gds without POLY2 / RES / LVSD (a resistor's two
    heads stay two nets; the body belongs to the resistor model), read like the bank."""
    global _RLOADS
    if _RLOADS is None:
        import cbcm_c
        import klayout.db as kdb
        ly = kdb.Layout()
        ly.read(RES_GDS)
        for li in ly.layer_indexes():
            if ly.get_info(li).layer in (13, 51, 60):
                ly.clear_layer(li)
        tmp = os.path.join(HERE, 'build', 'rores_nopoly2.gds')
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        ly.write(tmp)
        blk, _ = gen.build_res()
        i = gen.RES_I
        ex = cbcm_c.Extract(tmp, blk=blk, critical=lambda n: n[:1] in "mrt" and n[1:2].isdigit())
        nets = [f"m{i}_{s}" for s in range(1, gen.NST)] + [f"r{i}_{s}" for s in range(gen.NST)] + [f"t{i}", f"in{i}"]
        _RLOADS = {n: sum(cbcm_c.wiring(ks) for ks in cbcm_c.flat(ex.couplings(n)).values()) for n in nets}
    return _RLOADS


def res_netlist(which, corner, temp, rsh=125.0, body=1.0, vdd=5.0):
    """The resistor RO: which 'plan' (ro_bank.py's loads and resistor, plus the tap) or 'layout' (drawn
    wiring, drawn resistor with contacts and body capacitance x body)."""
    i = gen.RES_I
    order = {"INVX1": "A Y", "INVX4": "A Y", "NAND2X1": "A B Y"}
    n = header(corner, temp) + f"vdd vdd 0 {vdd}\nven en{i} 0 pwl(0 0 20n 0 20.5n {vdd})\n"
    for inst, cell, pins in gen.stage_nets(i, 'res'):
        nodes = [{"VDD": "vdd", "VSS": "0"}.get(pins[p], pins[p]) for p in order[cell].split()]
        n += f"{inst} {' '.join(nodes)} vdd 0 {cell}\n"
    sq, area, perim = res_geometry()
    cbody = body * (area * POLY_FIELD[0] + perim * POLY_FIELD[1])
    for inst, pins in gen.resistor_nets(i):
        a, b = pins['A'], pins['B']
        if which == 'plan':
            n += f"R{inst} {a} {b} {p2res(temp, 40, rsh):.3f}\n"
            continue
        p = [f"{inst}_p{k}" for k in range(NSEG + 1)]
        n += f"R{inst}_ca {a} {p[0]} {RCONT}\nR{inst}_cb {p[-1]} {b} {RCONT}\n"
        rseg = p2res(temp, sq, rsh) / NSEG
        for k in range(NSEG):
            n += f"R{inst}_{k} {p[k]} {p[k + 1]} {rseg:.4f}\n"
        if cbody > 0:
            for k, node in enumerate(p):
                c = cbody / NSEG / (2 if k in (0, NSEG) else 1)
                n += f"C{inst}_{k} {node} 0 {c:.4f}f\n"
    loads = {f"r{i}_{s}": 5.0 for s in range(gen.NST)} if which == 'plan' else res_wiring_loads()
    for net, c in loads.items():
        if c > 0:
            n += f"c_{net} {net} 0 {c:.3f}f\n"
    n += f""".control
set noaskquit
tran 0.05n 900n
meas tran t1 when v(r{i}_5)={vdd / 2} rise=6
meas tran t2 when v(r{i}_5)={vdd / 2} rise=16
let f = 10 / (t2 - t1)
meas tran iavg avg i(vdd) from=t1 to=t2
let p = -iavg * {vdd}
echo "RES f=$&f p=$&p"
quit
.endc
.end
"""
    return n


def job_res(args):
    which, corner, temp, rsh, body = args
    r = run(res_netlist(which, corner, temp, rsh, body), f"ror_{which}_{corner}_{temp}_{rsh:g}_{body:g}")
    return r.get('f', float('nan')), r.get('p', float('nan'))


def res_jobs():
    jobs = [('plan', 'TT', 27, 125.0, 1.0)]
    jobs += [('layout', c, 27, 125.0, 1.0) for c in CORNERS] + [('layout', 'TT', 125, 125.0, 1.0)]
    jobs += [('layout', 'TT', 27, rs, 1.0) for rs in (110.0, 140.0)] + [('layout', 'TT', 27, 125.0, 0.0)]
    return jobs


def res_report(res, out):
    """Print the resistor RO rows and add out['res'] (RES/INV per corner from the bank's INV RO)."""
    fp = res[('plan', 'TT', 27, 125.0, 1.0)][0]
    fl, pl = res[('layout', 'TT', 27, 125.0, 1.0)]
    rat = [res[('layout', c, 27, 125.0, 1.0)][0] / fl for c in ('SS', 'FF', 'SF', 'FS')]
    f125 = res[('layout', 'TT', 125, 125.0, 1.0)][0]
    loads = res_wiring_loads()
    i = gen.RES_I
    far = [loads[f"r{i}_{s}"] for s in range(1, gen.NST)]
    near = [loads[f"m{i}_{s}"] for s in range(1, gen.NST)]
    sq, area, perim = res_geometry()
    o = dict(plan=PLAN_RES, block=fp, layout=fl, ratios=rat, f125=f125, p=pl, node=(min(far), max(far)),
             near=(min(near), max(near)), rsh={rs: res[('layout', 'TT', 27, rs, 1.0)][0] for rs in (110.0, 140.0)},
             nobody=res[('layout', 'TT', 27, 125.0, 0.0)][0], squares=sq,
             cbody=area * POLY_FIELD[0] + perim * POLY_FIELD[1])
    print(f"{'res':5s} {PLAN_RES:9.1f} {fp / 1e6:8.1f} {fl / 1e6:8.1f} {100 * (fl / fp - 1):+6.1f}% " +
          ' '.join(f"{x:6.3f}" for x in rat) + f" {f125 / 1e6:7.1f} {pl * 1e3:5.1f}   {min(far):.1f}-{max(far):.1f}"
          f" (after the resistor; before it {min(near):.1f}-{max(near):.1f})")
    print(f"res: {sq:g} squares + 2 x {RCONT:g} ohm contacts, body {o['cbody']:.1f} fF ({NSEG} segments); "
          f"RSH 110 / 140 ohm/sq: {o['rsh'][110.0] / 1e6:.1f} / {o['rsh'][140.0] / 1e6:.1f} MHz; "
          f"without body capacitance {o['nobody'] / 1e6:.1f} MHz")
    if 'inv' in out:
        base = fl / out['inv']['layout']
        o['res_inv'] = {c: (res[('layout', c, 27, 125.0, 1.0)][0] / out['inv']['layout'] /
                            (out['inv']['ratios'][k] if c != 'TT' else 1.0)) / base - 1
                        for k, c in enumerate(['SS', 'FF', 'SF', 'FS'])}
        print("RES/INV (layout) vs TT: " + ", ".join(f"{c} {100 * v:+.1f} %" for c, v in o['res_inv'].items()) +
              f"; RSH 110 / 140: {100 * (o['rsh'][110.0] / fl - 1):+.1f} / {100 * (o['rsh'][140.0] / fl - 1):+.1f} %")
    out['res'] = o


def main():
    loads = wiring_loads()
    jobs = []
    for i, kind in gen.KINDS.items():
        jobs.append(('plan', i, kind, 'TT', 27))
        jobs += [('layout', i, kind, c, 27) for c in CORNERS] + [('layout', i, kind, 'TT', 125)]
    rjobs = res_jobs() if os.path.exists(RES_GDS) else []
    if rjobs:
        res_wiring_loads()
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(zip(jobs, ex.map(job, jobs)))
        rres = dict(zip(rjobs, ex.map(job_res, rjobs)))
    out = {}
    print(f"{'RO':5s} {'plan sim':>9s} {'block':>8s} {'layout':>8s} {'d':>7s} {'SS/TT':>6s} {'FF/TT':>6s} {'SF/TT':>6s} "
          f"{'FS/TT':>6s} {'125C':>7s} {'mW':>5s}   node wiring fF (min-max)")
    for i, kind in gen.KINDS.items():
        fp = res[('plan', i, kind, 'TT', 27)][0]
        fl, pl = res[('layout', i, kind, 'TT', 27)]
        rat = [res[('layout', i, kind, c, 27)][0] / fl for c in ('SS', 'FF', 'SF', 'FS')]
        f125 = res[('layout', i, kind, 'TT', 125)][0]
        node = [loads[f"r{i}_{s}"] for s in range(gen.NST)]
        out[kind] = dict(plan=PLAN[kind], block=fp, layout=fl, ratios=rat, f125=f125, p=pl, node=(min(node), max(node)))
        print(f"{kind:5s} {PLAN[kind]:9.1f} {fp / 1e6:8.1f} {fl / 1e6:8.1f} {100 * (fl / fp - 1):+6.1f}% " +
              ' '.join(f"{x:6.3f}" for x in rat) + f" {f125 / 1e6:7.1f} {pl * 1e3:5.1f}   {min(node):.1f}-{max(node):.1f}")
    nn = out['nand']['layout'] / out['nor']['layout']
    print(f"NAND/NOR TT: plan {PLAN['nand'] / PLAN['nor']:.3f}, layout {nn:.3f}; "
          f"tap and t / in wiring (fF): " + ", ".join(f"in{i} {loads[f'in{i}']:.1f}" for i in gen.KINDS))
    if rres:
        res_report(rres, out)
    else:
        print(f"resistor RO: {RES_GDS} not found (python3 designs/etri050/gen/etri050_ro.py --block rores)")
    return out


if __name__ == '__main__':
    main()
