"""CBCM block as drawn by designs/etri050/gen/etri050_cbcm.py, before layout extraction.

The plan checked the principle with one pseudo-inverter pair (cbcm.py). This runs the block's own
schematic netlist: the plan's non-overlap generator, the per-cell PMOS clock gate NAND2X1(PCK, en<i>),
the global NMOS gate NG, and all ten cells with models of their structures on ND<i>:
  PIP (pipcap_i COX, CAPSW over the 30 x 30 um plate) and the metal structures as ideal capacitors of
  their rule-document value (the drawn values come from cbcm_c.py after layout); the N+ structures as
  the PDK ndiode with their planned area and perimeter; the gates as nmos4 with S, D, B at VSS.
"True" values are Q(V)/V of the same models charged from 0 to V through an ideal source.

Checks
  gaps      non-overlap between NMOS off and PMOS on (and back) at the selected cell's gates:
            5 corners at 27 C, TT / SS / FF at 125 C, VDD 4.5 / 5.5 V at TT / SS / FF, clock 0.2 / 1 / 5 MHz
  accuracy  every cell at 1 MHz, 5 V, TT 27 C against its true Q(V)/V; empty cell offset
  idle      clock stopped and no cell selected: VCD and VCR currents
  others    cell 2 alone vs with every other structure present (unselected cells must not count)
  pad       PADR (725 ohm) in both supply pins: change for cells 2 and 8
  c-v       cell 8 (gate W 48 / L 10.5) at VCD 1.5-5 V against its true Q(V)/V

Result (ngspice-42, 2026-11-01): 300 fF cells +1.49 %, PIP +1.0 %, N+ +0.3 / +0.75 %, gates +0.2 %,
empty cell 0.00 fF; non-overlap 0.30 ns at least (FF, VDD 4.5 V); PADR +0.24 %p; C-V within 0.51 %.
"""
from concurrent.futures import ProcessPoolExecutor
import os
import re
import sys

from simlib import BUILD, geo, header, run

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'gen'))
import etri050_cbcm as gen  # noqa: E402

# planned structure values (cbcm_c.py replaces them with the drawn geometry)
PIP_C = 0.5e-15 * 900 + 0.09e-15 * 120          # pipcap_i: COX 5e-4 F/m2, CAPSW 9e-11 F/m
IDEAL = {1: PIP_C, 2: 301e-15, 3: 300e-15, 4: 300e-15, 5: 300e-15}
DIODE = {6: (404e-12, 80.4e-6), 7: (242e-12, 481e-6)}      # area m2, perimeter m (planned)
VTN, VTP = 0.7, 0.9      # gate levels where the NMOS starts to conduct (NG) and the PMOS (VCD - PG)


def block_netlist():
    """The block subcircuit with simulation models: nfet/pfet -> nmos4/pmos4, junctions on the pairs."""
    out = []
    for line in gen.netlist(with_cells=False).splitlines():
        if line.startswith('M'):
            parts = line.split()
            model = {'nfet': 'nmos4', 'pfet': 'pmos4'}[parts[5]]
            w = float(re.search(r'W=([\d.]+)u', line).group(1))
            line = ' '.join(parts[:5] + [model] + parts[6:]) + ' ' + geo(w)
        out.append(line)
    return '\n'.join(out) + '\n'


def structures(cells=range(gen.NCELL)):
    s = ''
    for i in cells:
        if i in IDEAL:
            s += f"cs{i} ND{i} 0 {IDEAL[i]:.4e}\n"
        elif i in DIODE:
            a, p = DIODE[i]
            s += f"ds{i} 0 ND{i} ndiode area={a:.4e} pj={p:.4e}\n"
    s += "cpar 0 0 1f\n"
    return s


def netlist(sel, vddm=5.0, f=1e6, corner='TT', temp=27, vdd=5.0, rpad=0.0, cells=range(gen.NCELL), clock=True):
    per = 1.0 / f
    # abstol 1e-13 A (simlib: 1e-15): with 1e-15 two runs (FF 27 C, PADR) stopped with "timestep too
    # small" at 9.5 us; 1e-13 gives the same C to 0.01 fF where both finish (TT: 305.51 fF)
    n = header(corner, temp, extra=".lib '05cmos_model_260210.lib' DIODE", reltol='1e-5', method='gear',
               abstol='1e-13')
    n += block_netlist()
    n += f"vdd vdd 0 {vdd}\n"
    if clock:
        n += f"vck clk 0 pulse(0 {vdd} 0 2n 2n {per / 2 - 2e-9:.4e} {per:.4e})\n"
    else:
        n += "vck clk 0 0\n"
    for i in range(gen.NCELL):
        n += f"ve{i} en{i} 0 {vdd if i == sel else 0}\n"
    if rpad > 0:
        n += f"vdut vpd 0 {vddm}\nvref vpr 0 {vddm}\nrsd vpd vcd {rpad}\nrsr vpr vcr {rpad}\n"
    else:
        n += f"vdut vcd 0 {vddm}\nvref vcr 0 {vddm}\n"
    n += "xb clk " + ' '.join(f"en{i}" for i in range(gen.NCELL)) + " vcd vcr vdd 0 cbcm\n"
    # the structures sit on the block's internal nodes: expose them through the instance
    n += structures(cells).replace(' ND', ' xb.ND')
    t0, t1 = 3 * per, 23 * per
    k = sel if sel is not None else 0
    n += f""".control
set noaskquit
tran {per / 400:.4e} {t1:.4e}
meas tran id avg i(vdut) from={t0:.4e} to={t1:.4e}
meas tran ir avg i(vref) from={t0:.4e} to={t1:.4e}
let c = (ir - id) / ({vddm} * {f})
meas tran tnf when v(xb.NG)={VTN} fall=5
meas tran tpf when v(xb.PG{k})={vddm - VTP:.3f} fall=5
meas tran tpr when v(xb.PG{k})={vddm - VTP:.3f} rise=5
meas tran tnr when v(xb.NG)={VTN} rise=5
meas tran hnf when v(xb.NG)={vdd / 2} fall=5
meas tran hpf when v(xb.PG{k})={vdd / 2} fall=5
let gap_on = tpf - tnf
let gap_off = tnr - tpr
let gap_half = hpf - hnf
echo "RES c=$&c id=$&id ir=$&ir gap_on=$&gap_on gap_off=$&gap_off gap_half=$&gap_half"
quit
.endc
.end
"""
    return n


def truth_netlist(i, v, corner='TT', temp=27):
    """Q(V)/V of structure i's model: node charged 0 -> v in 200 ns by an ideal source."""
    n = header(corner, temp, extra=".lib '05cmos_model_260210.lib' DIODE", reltol='1e-6')
    n += f"vx x 0 pwl(0 0 200n {v})\n"
    if i in IDEAL:
        n += f"cs x 0 {IDEAL[i]:.4e}\n"
    elif i in DIODE:
        a, p = DIODE[i]
        n += f"ds 0 x ndiode area={a:.4e} pj={p:.4e}\n"
    else:
        w, l, nf = gen.GATE_L10 if i == 8 else gen.GATE_L2
        n += ''.join(f"mg{k} 0 x 0 0 nmos4 w={w}u l={l}u {geo(w)}\n" for k in range(nf))
    n += f""".control
set noaskquit
tran 0.2n 220n
meas tran q integ i(vx) from=0 to=220n
let c = -q / {v}
echo "RES c=$&c"
quit
.endc
.end
"""
    return n


def job(args):
    kind = args[0]
    if kind == 'truth':
        _, i, v = args
        return run(truth_netlist(i, v), f"cbcmb_true_{i}_{v}").get('c', float('nan'))
    _, sel, kw = args
    tag = 'cbcmb_' + '_'.join(f"{k}{v}" for k, v in sorted(kw.items()) if k != 'cells') + f"_s{sel}"
    if 'cells' in kw:
        tag += '_c' + ''.join(map(str, kw['cells']))
    tag = tag.replace(' ', '').replace('.', 'p')
    r = run(netlist(sel, **kw), tag)
    log = open(os.path.join(BUILD, tag + '.log')).read()
    if 'Timestep too small' in log or 'out of interval' in log.split('RES')[0]:
        r = {k: float('nan') for k in ('c', 'id', 'ir', 'gap_on', 'gap_off')}   # did not reach the end
    return r


def main():
    jobs = {}
    for i in range(gen.NCELL):
        jobs[('acc', i)] = ('meas', i, {})
        if i:
            jobs[('true', i)] = ('truth', i, 5.0)
    for corner in ('SS', 'FF', 'SF', 'FS'):
        jobs[('corner', corner, 27)] = ('meas', 2, dict(corner=corner))
    for corner in ('TT', 'SS', 'FF'):
        jobs[('corner', corner, 125)] = ('meas', 2, dict(corner=corner, temp=125))
    for corner in ('TT', 'SS', 'FF'):
        for vdd in (4.5, 5.5):
            jobs[('vdd', corner, vdd)] = ('meas', 2, dict(corner=corner, vdd=vdd))
    for f in (0.2e6, 5e6):
        jobs[('freq', f)] = ('meas', 2, dict(f=f))
    jobs[('idle',)] = ('meas', None, dict(clock=False))
    jobs[('alone',)] = ('meas', 2, dict(cells=[2]))
    for i in (2, 8):
        jobs[('pad', i)] = ('meas', i, dict(rpad=725.0))
    volts = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    for v in volts:
        jobs[('cv', v)] = ('meas', 8, dict(vddm=v))
        jobs[('cvtrue', v)] = ('truth', 8, v)
    keys = list(jobs)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        vals = dict(zip(keys, ex.map(job, [jobs[k] for k in keys])))

    out = {}
    print(f"{'cell':4s} {'structure':14s} {'true fF':>9s} {'CBCM fF':>9s} {'err fF':>7s} {'err %':>7s}")
    for i in range(gen.NCELL):
        c = vals[('acc', i)].get('c', float('nan'))
        t = vals.get(('true', i), 0.0)
        out[('acc', i)] = (c, t)
        pct = f"{100 * (c / t - 1):+7.2f}" if t else '      -'
        print(f"{i:4d} {gen.STRUCTURES[i]:14s} {t * 1e15:9.2f} {c * 1e15:9.2f} {(c - t) * 1e15:+7.2f} {pct}")
    gaps = []
    for k in [('acc', 2)] + [k for k in keys if k[0] in ('corner', 'vdd', 'freq')]:
        r = vals[k]
        gaps.append((k, r.get('gap_on', float('nan')), r.get('gap_off', float('nan')), r.get('c', float('nan'))))
    print("non-overlap at the cell 2 gates (NG at VTN, PG at VCD - VTP) and cell 2 error:")
    for k, on, off, c in gaps:
        t = vals[('true', 2)]
        print(f"  {str(k):28s} NMOS off -> PMOS on {on * 1e9:6.2f} ns, PMOS off -> NMOS on {off * 1e9:6.2f} ns,"
              f" C err {100 * (c / t - 1):+.2f} %")
    out['gap_min'] = min(min(on, off) for _, on, off, _ in gaps)
    r = vals[('idle',)]
    out['idle'] = (r.get('id', float('nan')), r.get('ir', float('nan')))
    print(f"idle (no clock, no cell): I(VCD) {-out['idle'][0] * 1e12:.3f} pA, I(VCR) {-out['idle'][1] * 1e12:.3f} pA")
    a, b = vals[('alone',)]['c'], vals[('acc', 2)]['c']
    out['others'] = 100 * (b - a) / a
    print(f"cell 2 with every other structure present vs alone: {out['others']:+.4f} %")
    for i in (2, 8):
        p = vals[('pad', i)]['c']
        c = vals[('acc', i)]['c']
        out[('pad', i)] = 100 * (p - c) / vals[('true', i)]
        print(f"PADR 725 ohm, cell {i}: change {out[('pad', i)]:+.3f} %p")
    out['cv'] = []
    for v in volts:
        c, t = vals[('cv', v)].get('c', float('nan')), vals[('cvtrue', v)]
        out['cv'].append((v, c, t))
        print(f"C-V cell 8 at {v:.1f} V: CBCM {c * 1e12:.4f} pF, true Q/V {t * 1e12:.4f} pF, {100 * (c / t - 1):+.2f} %")
    return out


if __name__ == '__main__':
    main()
