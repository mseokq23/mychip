"""Charge-based capacitance measurement (CBCM) cell built from kit standard cells.

Non-overlap clock generator (INVX1, NOR2X1, 4-inverter delays, INVX4 drivers) drives two
pseudo-inverters (PMOS 6/0.6, NMOS 3/0.6): DUT with the structure under test, REF without.
C = (I_DUT - I_REF) / (V * f) from the average supply currents.

Checks
  accuracy   C = 10 fF ... 3 pF at 1 MHz, 27 C (gear, reltol 1e-5)
  frequency  300 fF and 1 pF at 0.2 / 1 / 5 MHz
  pad        the same with the PANA series resistor (PADR, ~725 ohm) in both supply pins
  hot        1 pF at 125 C
  c-v        gate structure W 50 / L 10 um: dQ/dV from VDD_DUT steps vs the model Cgg
"""
from concurrent.futures import ProcessPoolExecutor
import os

import re

import numpy as np

from simlib import BUILD, geo, header, run

NOVL = """
xi0 clk clkb vdd 0 INVX1
xn1 clk d2 p1 vdd 0 NOR2X1
xn2 clkb d1 p2 vdd 0 NOR2X1
xa1 p1 a1 vdd 0 INVX1
xa2 a1 a2 vdd 0 INVX1
xa3 a2 a3 vdd 0 INVX1
xa4 a3 d1 vdd 0 INVX1
xb1 p2 b1 vdd 0 INVX1
xb2 b1 b2 vdd 0 INVX1
xb3 b2 b3 vdd 0 INVX1
xb4 b3 d2 vdd 0 INVX1
xv2a p1 v2b vdd 0 INVX1
xv2b v2b v2 vdd 0 INVX4
xv1a p2 v1 vdd 0 INVX4
"""


def netlist(cdut, vddm=5.0, f=1e6, temp=27, rpad=0.0, mos=None):
    per = 1.0 / f
    n = header('TT', temp, reltol='1e-5', method='gear')
    n += f"vdd vdd 0 5\nvck clk 0 pulse(0 5 0 2n 2n {per / 2 - 2e-9:.4e} {per:.4e})\n" + NOVL
    if rpad > 0:
        n += f"vdut vpd 0 {vddm}\nvref vpr 0 {vddm}\nrsd vpd vddd {rpad}\nrsr vpr vddr {rpad}\n"
    else:
        n += f"vdut vddd 0 {vddm}\nvref vddr 0 {vddm}\n"
    n += f"mpd nd v1 vddd vddd pmos4 w=6u l=0.6u {geo(6)}\nmnd nd v2 0 0 nmos4 w=3u l=0.6u {geo(3)}\n"
    n += f"mpr nr v1 vddr vddr pmos4 w=6u l=0.6u {geo(6)}\nmnr nr v2 0 0 nmos4 w=3u l=0.6u {geo(3)}\n"
    n += "cpd nd 0 5f\ncpr nr 0 5f\n"
    if mos:
        w, l = mos
        n += f"mg 0 nd 0 0 nmos4 w={w}u l={l}u {geo(w)}\n"
    else:
        n += f"ct nd 0 {cdut}\n"
    t0, t1 = 3 * per, 23 * per
    n += f""".control
set noaskquit
tran {per / 400:.4e} {t1:.4e}
meas tran id avg i(vdut) from={t0:.4e} to={t1:.4e}
meas tran ir avg i(vref) from={t0:.4e} to={t1:.4e}
let c = (ir - id) / ({vddm} * {f})
echo "RES c=$&c"
quit
.endc
.end
"""
    return n


def measure(args):
    cdut, vddm, f, temp, rpad, mos = args
    tag = f"cbcm_{cdut}_{vddm}_{f:.0f}_{temp}_{rpad:.0f}_{mos}".replace('(', '').replace(')', '').replace(', ', 'x')
    return run(netlist(cdut, vddm, f, temp, rpad, mos), tag).get('c', float('nan'))


def cgg_model(w, l, volts):
    net = header('TT', 27) + f"vg g 0 0\nmg 0 g 0 0 nmos4 w={w}u l={l}u {geo(w)}\n.control\nset noaskquit\n"
    for k, v in enumerate(volts):
        net += f"alter vg dc = {v}\nop\nlet cg = @mg[cgg]\necho \"RES c{k}=$&cg\"\n"
    net += "quit\n.endc\n.end\n"
    r = run(net, 'cgg_ref')
    return np.array([r[f"c{k}"] for k in range(len(volts))])


def overlap(w, l):
    """Gate overlap capacitance from the NMOS model card: (CGSO + CGDO) W_eff + 2 CGBO L_eff."""
    txt = open(f"{BUILD}/05cmos_mosfet_corner.lib").read()
    sect = txt[txt.index('.LIB MOS'):]

    def par(name):
        return float(re.search(r'\b%s\s*=\s*([-+0-9.Ee]+)' % name, sect).group(1))
    weff = w * 1e-6 - 2 * par('WINT')
    leff = l * 1e-6 - 2 * par('LINT')
    return (par('CGSO') + par('CGDO')) * weff + 2 * par('CGBO') * leff


def main():
    jobs = {}
    for c in (10e-15, 100e-15, 300e-15, 1e-12, 3e-12):
        jobs[('acc', c)] = (c, 5.0, 1e6, 27, 0.0, None)
    for c in (300e-15, 1e-12):
        for f in (0.2e6, 5e6):
            jobs[('freq', c, f)] = (c, 5.0, f, 27, 0.0, None)
        for f in (1e6, 5e6):
            jobs[('pad', c, f)] = (c, 5.0, f, 27, 725.0, None)
    jobs[('hot', 1e-12)] = (1e-12, 5.0, 1e6, 125, 0.0, None)
    volts = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    for v in volts:
        jobs[('cv', v)] = (None, v, 1e6, 27, 0.0, (50, 10))
    keys = list(jobs)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        vals = dict(zip(keys, ex.map(measure, [jobs[k] for k in keys])))
    out = {}
    for c in (10e-15, 100e-15, 300e-15, 1e-12, 3e-12):
        m = vals[('acc', c)]
        out[('acc', c)] = m
        print(f"accuracy  C={c * 1e15:6.0f} fF  meas {m * 1e15:8.2f} fF  err {1e15 * (m - c):+5.2f} fF ({100 * (m / c - 1):+.2f} %)")
    for c in (300e-15, 1e-12):
        base = vals[('acc', c)]
        for f in (0.2e6, 5e6):
            m = vals[('freq', c, f)]
            print(f"frequency C={c * 1e15:6.0f} fF  {f / 1e6:3.1f} MHz  err {100 * (m / c - 1):+.2f} % (1 MHz {100 * (base / c - 1):+.2f} %)")
        for f in (1e6, 5e6):
            m = vals[('pad', c, f)]
            ref = base if f == 1e6 else vals[('freq', c, f)]
            out[('pad', c, f)] = 100 * (m - ref) / c
            print(f"PADR      C={c * 1e15:6.0f} fF  {f / 1e6:3.1f} MHz  err {100 * (m / c - 1):+.2f} %  change {out[('pad', c, f)]:+.2f} %p")
    m = vals[('hot', 1e-12)]
    print(f"125 C     C=  1000 fF  err {100 * (m / 1e-12 - 1):+.2f} %")
    q = np.array([vals[('cv', v)] * v for v in volts])
    vv = np.array(volts)
    mid = (vv[1:] + vv[:-1]) / 2
    cq = np.diff(q) / np.diff(vv)
    cg = np.interp(mid, vv, cgg_model(50, 10, volts))
    cov = overlap(50, 10)
    print(f"C-V  model overlap (CGSO, CGDO, CGBO) for W 50 / L 10: {cov * 1e15:.1f} fF")
    for v, a, b in zip(mid, cq, cg):
        note = '  (PMOS does not charge fully below 1.5 V)' if v < 1.5 else ''
        print(f"C-V  V={v:.2f}  CBCM {a * 1e12:.4f} pF  model Cgg + overlap {(b + cov) * 1e12:.4f} pF  "
              f"diff {100 * (a / (b + cov) - 1):+.2f} %{note}")
    out['cv'] = [(v, a, b + cov) for v, a, b in zip(mid, cq, cg)]
    return out


if __name__ == '__main__':
    main()
