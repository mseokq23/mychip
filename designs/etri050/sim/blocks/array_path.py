"""Kelvin array path: how much the switches, pads and unselected cells disturb a measurement.

Model: 8 x 8 NMOS block of the array (one geometry per run), row gate transmission gates
(N 6 / P 15 um), unselected rows parked at 0 V, column force TG N 100 / P 250 um and sense
TG N 6 / P 15 um, unselected columns parked to the source mesh, PANA pads with the ESD
diodes of the kit GPIO cell (12 x 10 x 10 um per polarity, from the GDS), ideal Kelvin
source-measure units, and an identical isolated reference device with ideal bias.

Reported per geometry / VDS / corner / temperature:
  on_err   largest |I_array - I_ref| / I_ref for VG >= 1.5 V
  dvt      threshold difference at I = 0.1 uA * W/L
  i0       path current at VG = 0 (leakage floor)
  dvt_cor  threshold difference after subtracting an open channel (same column, no devices)
"""
import math

import numpy as np

from simlib import BUILD, geo, header, run

PANA = """
.subckt pana pad vdd vss
dn vss pad ndiode area=1200p pj=480u
dp pad vdd pdiode area=1200p pj=480u
.ends
"""


def tgate(name, a, b, en, enb, wn, wp):
    return (f"mn{name} {a} {en} {b} 0 nmos4 w={wn}u l=0.6u {geo(wn)}\n"
            f"mp{name} {a} {enb} {b} vdd pmos4 w={wp}u l=0.6u {geo(wp)}\n")


def netlist(w, l, vds, corner, temp, out, open_col=False, ncol=8, nrow=8):
    n = header(corner, temp, ".lib '05cmos_model_260210.lib' DIODE") + PANA + "vdd vdd 0 5\n"
    for p in ('pdf', 'pds', 'psf', 'pss', 'pg'):
        n += f"x{p} {p} vdd 0 pana\n"
    # Kelvin units: the force node is driven until the sense node equals the set value
    n += f"vdset dset 0 {vds}\nedf dfo 0 dset pds 1e5\nvmd dfo pdf 0\n"
    n += "esf sfo 0 0 pss 1e5\nvms sfo psf 0\nvg pg 0 0\n"
    # pad-to-array routing (estimates)
    n += "rdf pdf bdf 2\nrds pds bds 10\nrsf psf smesh 2\nrss pss sstap 10\nrsm sstap smesh 0.2\nrg pg bg 10\n"
    n += tgate('rg', 'bg', 'row0', 'vdd', '0', 6, 15)
    for r in range(1, nrow):
        n += f"mpk{r} row{r} vdd 0 0 nmos4 w=3u l=0.6u {geo(3)}\n"
    for c in range(ncol):
        en, enb = ('vdd', '0') if c == 0 else ('0', 'vdd')
        n += tgate(f'f{c}', 'bdf', f'col{c}', en, enb, 100, 250)
        n += tgate(f's{c}', 'bds', f'cs{c}', en, enb, 6, 15)
        n += f"rcs{c} cs{c} col{c} 1\n"
        n += f"mpc{c} col{c} {enb} smesh 0 nmos4 w=3u l=0.6u {geo(3)}\n"
        if not (open_col and c == 0):
            for r in range(nrow):
                n += f"md{c}_{r} col{c} row{r} smesh 0 nmos4 w={w}u l={l}u {geo(w)}\n"
    n += f"vrd rd 0 {vds}\nmref rd pg 0 0 nmos4 w={w}u l={l}u {geo(w)}\n"
    n += f""".control
set noaskquit
dc vg 0 5 0.02
let iarr = i(vmd)
let iref = -i(vrd)
wrdata {out} v(pg) iarr iref
quit
.endc
.end
"""
    return n


def sweep(w, l, vds, corner, temp, open_col=False):
    tag = f"arr_{w}_{l}_{vds}_{corner}_{temp}_{int(open_col)}"
    run(netlist(w, l, vds, corner, temp, tag + '.dat', open_col), tag)
    d = np.loadtxt(f"{BUILD}/{tag}.dat")
    return d[:, 1], d[:, 3], d[:, 5]


def vt(vg, i, ithr):
    idx = np.where(i > ithr)[0]
    if len(idx) == 0 or idx[0] == 0:
        return float('nan')
    k = idx[0]
    a, b = math.log(abs(i[k - 1]) + 1e-30), math.log(i[k])
    return vg[k - 1] + (math.log(ithr) - a) / (b - a) * (vg[k] - vg[k - 1])


def check(w, l, vds, corner, temp, with_open=False):
    vg, ia, ir = sweep(w, l, vds, corner, temp)
    ithr = 0.1e-6 * w / l
    on = vg >= 1.5
    res = dict(on_err=100 * float(np.max(np.abs(ia[on] - ir[on]) / ir[on])),
               dvt=1e3 * (vt(vg, ia, ithr) - vt(vg, ir, ithr)), i0=float(ia[0]), i0_ref=float(ir[0]))
    if with_open:
        _, io, _ = sweep(w, l, vds, corner, temp, open_col=True)
        res['i_open'] = float(io[0])
        res['dvt_cor'] = 1e3 * (vt(vg, ia - io, ithr) - vt(vg, ir, ithr))
    return res


CASES = [(w, l, vds, c, t) for (w, l) in [(9, 0.6), (3, 3), (18, 18)] for vds in (0.1, 4.5)
         for (c, t) in (('TT', 27), ('TT', 125), ('FF', 125))]


def main():
    out = {}
    for (w, l, vds, c, t) in CASES:
        r = check(w, l, vds, c, t, with_open=(t == 125))
        out[(w, l, vds, c, t)] = r
        extra = f"  open {r['i_open']:.2e} A -> dVt {r['dvt_cor']:+.3f} mV" if 'dvt_cor' in r else ''
        print(f"W/L {w}/{l} VDS {vds} {c} {t:3d} C: on-err {r['on_err']:.4f} %  dVt {r['dvt']:+.3f} mV  "
              f"I(VG=0) {r['i0']:.2e} A{extra}", flush=True)
    return out


if __name__ == '__main__':
    main()
