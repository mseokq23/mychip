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

usage: python3 ro_post.py   (needs designs/etri050/ro/build/robank_flat.gds: run etri050_ro.py first)
"""
from concurrent.futures import ProcessPoolExecutor
import os
import sys

from simlib import header, run

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


def main():
    loads = wiring_loads()
    jobs = []
    for i, kind in gen.KINDS.items():
        jobs.append(('plan', i, kind, 'TT', 27))
        jobs += [('layout', i, kind, c, 27) for c in CORNERS] + [('layout', i, kind, 'TT', 125)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(zip(jobs, ex.map(job, jobs)))
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
    return out


if __name__ == '__main__':
    main()
