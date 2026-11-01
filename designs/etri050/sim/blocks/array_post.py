"""Kelvin array path after layout: array_path.py's harness with the drawn array's parasitics.

What changes from array_path.py (which modelled the plan's array with ideal lines and an ideal
source mesh):
  - per-cell drain sense TG N 3 / P 7.5 um onto the column sense line (as drawn; array_kelvin.py
    showed it is needed), D<c> as MET2 line segments (6 um wide, one row pitch each);
  - the path resistances extracted from the drawn layout for the measured cell
    (designs/etri050/array/kelvin_r.py): source MET1/VIA1/MET2/VIA2/plate up to the ASS sense point,
    and the drain strip between the force via and the sense tap; contacts in series with both the
    array cell and the reference device (they belong to the device as drawn);
  - drawn switch sizes: force TG N 100.8 / P 252 um, row parking NMOS W 6 um, column parking TG
    N 3 / P 7.5 um.
The measured cell is row 0 of its column with the largest path resistance of that column's NMOS
rows (typ or max sheet/via values). Reported as in array_path.py: on-current error against the
reference for VG >= 1.5 V, threshold difference, and the R_tot error at VG = 5 V, VDS = 0.1 V;
'corrected' compares with the reference given the typ path resistance, i.e. after subtracting
the extracted table, when the process sits at the max values.
"""
import json
import math
import os

import numpy as np

from array_path import PANA, tgate, vt
from simlib import BUILD, REPO, geo, header, run

KELVIN_R = os.path.join(REPO, 'designs/etri050/array/build/kelvin_r.json')
ROW_PITCH = 34.5           # um, NMOS rows
MET2_RSH = 0.08
COLS = {(9, 0.6): 0, (3, 3): 4, (18, 18): 6}      # geometry -> array column


def path_values(col, corner, table):
    cells = [x for x in table['cells'] if x['col'] == col and x['corner'] == corner and x['type'] == 'nmos']
    return max(cells, key=lambda x: x['r_path'])


def netlist(w, l, vds, corner, temp, out, cell, ref_cell, open_col=False, ncol=8, nrow=8):
    rseg = ROW_PITCH / 6.0 * MET2_RSH
    rc = 2 * cell['r_d_cont']
    rb = 4 * -cell['r_d_metal'] / (1 - 2 * -cell['r_d_metal'] / rc)
    n = header(corner, temp, ".lib '05cmos_model_260210.lib' DIODE") + PANA + "vdd vdd 0 5\n"
    if temp > 100:     # the open column's force node only carries nA of leakage: ngspice's DC sweep
        n = n.replace('gmin=1e-15', 'gmin=1e-13')    # stalls at 1e-15; both runs of a pair use 1e-13
    for p in ('pdf', 'pds', 'psf', 'pss', 'pg'):
        n += f"x{p} {p} vdd 0 pana\n"
    n += f"vdset dset 0 {vds}\nedf dfo 0 dset pds 1e5\nvmd dfo pdf 0\n"
    n += "esf sfo 0 0 pss 1e5\nvms sfo psf 0\nvg pg 0 0\n"
    n += "rdf pdf bdf 2\nrds pds bds 10\nrsf psf ass 2\nrss pss ass 10\nrg pg bg 10\n"
    n += tgate('rg', 'bg', 'row0', 'vdd', '0', 6, 15)
    for r in range(1, nrow):
        n += f"mpk{r} row{r} vdd 0 0 nmos4 w=6u l=0.6u {geo(6)}\n"
    for c in range(ncol):
        en, enb = ('vdd', '0') if c == 0 else ('0', 'vdd')
        n += tgate(f'f{c}', 'bdf', f'c{c}_0', en, enb, 100.8, 252)
        n += tgate(f's{c}', 'bds', f'ds{c}', en, enb, 6, 15)
        n += f"mpcn{c} c{c}_0 {enb} ass 0 nmos4 w=3u l=0.6u {geo(3)}\n"
        n += f"mpcp{c} c{c}_0 {en} ass vdd pmos4 w=7.5u l=0.6u {geo(7.5)}\n"
        for r in range(nrow):
            if r < nrow - 1:
                n += f"rl{c}_{r} c{c}_{r} c{c}_{r + 1} {rseg:.4f}\n"
            on = (r == 0)
            n += tgate(f't{c}_{r}', f'ds{c}', f'b{c}_{r}', 'vdd' if on else '0', '0' if on else 'vdd', 3, 7.5)
            # drain strip, lumped: force via -> top contacts (t) -> strip rb -> bottom contacts (b) = the
            # sense tap; each half of the contacts 2 * r_d_cont. rb gives the extracted sense offset:
            # mean V(contacts) - V(b) = I * rb / (4 + 2 rb / rc) = -I * r_d_metal
            n += f"rdf{c}_{r} c{c}_{r} t{c}_{r} 0.05\n"
            n += f"rdb{c}_{r} t{c}_{r} b{c}_{r} {rb:.5f}\n"
            n += f"rdt{c}_{r} t{c}_{r} dd{c}_{r} {rc:.4f}\nrdbc{c}_{r} b{c}_{r} dd{c}_{r} {rc:.4f}\n"
            if open_col and c == 0:          # open column: the cell without its DUT
                continue
            n += f"md{c}_{r} dd{c}_{r} row{r} ss{c}_{r} 0 nmos4 w={w}u l={l}u {geo(w)}\n"
            n += f"rsc{c}_{r} ss{c}_{r} sm{c}_{r} {cell['r_s_cont']}\n"
            n += f"rsm{c}_{r} sm{c}_{r} ass {cell['r_s_metal']}\n"
    # reference: the same device with its contacts and, for 'corrected', the typ path resistances
    n += f"vrd rd 0 {vds}\nrrd rd rdd {ref_cell['r_d_cont'] + ref_cell.get('r_d_metal_ref', 0.0)}\n"
    n += f"mref rdd pg rss 0 nmos4 w={w}u l={l}u {geo(w)}\nrrs rss 0 {ref_cell['r_s_cont'] + ref_cell.get('r_s_metal_ref', 0.0)}\n"
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


def sweep(w, l, vds, corner, temp, cell, ref_cell, tag, open_col=False):
    run(netlist(w, l, vds, corner, temp, tag + '.dat', cell, ref_cell, open_col), tag)
    d = np.loadtxt(f"{BUILD}/{tag}.dat")
    return d[:, 1], d[:, 3], d[:, 5]


def compare(vg, ia, ir, w, l):
    ithr = 0.1e-6 * w / l
    on = vg >= 1.5
    return dict(on_err=100 * float(np.max(np.abs(ia[on] - ir[on]) / ir[on])),
                dvt=1e3 * (vt(vg, ia, ithr) - vt(vg, ir, ithr)), r_err=100 * float(ir[-1] / ia[-1] - 1))


def main():
    if not os.path.exists(KELVIN_R):
        raise SystemExit(f'{KELVIN_R} not found: build the array and run designs/etri050/array/kelvin_r.py')
    table = json.load(open(KELVIN_R))
    out = {}
    for (w, l), col in COLS.items():
        typ, mx = path_values(col, 'typ', table), path_values(col, 'max', table)
        for vds in (0.1, 4.5):
            for corner, temp in (('TT', 27), ('TT', 125)):
                res = {}
                for name, cell, ref in (('typ', typ, typ), ('max', mx, mx),
                                        ('corrected', mx, dict(mx, r_s_metal_ref=typ['r_s_metal'],
                                                               r_d_metal_ref=typ['r_d_metal']))):
                    tag = f"post_{w}_{l}_{vds}_{corner}_{temp}_{name}"
                    vg, ia, ir = sweep(w, l, vds, corner, temp, cell, ref, tag)
                    res[name] = compare(vg, ia, ir, w, l)
                    if temp > 100:   # leakage: subtract the open column, as array_path.py does
                        _, io, _ = sweep(w, l, vds, corner, temp, cell, ref, tag + '_open', open_col=True)
                        res[name]['dvt_cor'] = 1e3 * (vt(vg, ia - io, 0.1e-6 * w / l) - vt(vg, ir, 0.1e-6 * w / l))
                out[(w, l, vds, corner, temp)] = res
                line = '  '.join(f"{k}: on-err {v['on_err']:.3f} %, dVt {v['dvt']:+.3f} mV"
                                 + (f" (open subtracted {v['dvt_cor']:+.3f})" if 'dvt_cor' in v else '')
                                 + (f", R_tot {v['r_err']:+.3f} %" if vds < 1 else '') for k, v in res.items())
                print(f"W/L {w}/{l} (col {col}, path {typ['r_path']:.3f}/{mx['r_path']:.3f} ohm) VDS {vds} "
                      f"{corner} {temp:3d} C  {line}", flush=True)
    return out


if __name__ == '__main__':
    main()
