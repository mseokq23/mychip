#!/usr/bin/env python3
"""Run every block check and compare with the values recorded in the chip plan.

usage: python3 run_all.py [tg array kelvin post cbcm cbcm_block cbcm_post ro ro_post scan pnp lsplit]   (default:
all; post only when designs/etri050/array/build/kelvin_r.json exists (designs/etri050/array/kelvin_r.py),
cbcm_post when designs/etri050/cbcm/build/cbcm_c.json exists (designs/etri050/cbcm/cbcm_c.py), ro_post when
designs/etri050/ro/build/robank_flat.gds exists (designs/etri050/gen/etri050_ro.py))

Each line ends with ok or CHECK. CHECK means the result moved outside the tolerance
(for example a different ngspice version or model file) and needs a look, not that the
circuit failed. Logs and netlists are in build/.
"""
import os
import sys
import time

import array_kelvin
import array_path
import array_post
import cbcm
import cbcm_block
import cbcm_post
import ro_post
import lsplit
import pnp_thermo
import ro_bank
import scan_divider
import tg_ron

ROWS = []


def expect(name, value, ref, tol, unit=''):
    good = abs(value - ref) <= tol
    ROWS.append((name, value, ref, tol, unit, good))


def expect_max(name, value, limit, unit=''):
    good = value <= limit
    ROWS.append((name, value, limit, None, unit, good))


def expect_min(name, value, limit, unit=''):
    good = value >= limit
    ROWS.append((name, value, limit, 'min', unit, good))


def run_tg():
    r = tg_ron.main()
    expect('TG N100/P250 Ron max TT 27 C', r[(100, 250, 'TT', 27)], 45.4, 1.5, 'ohm')
    expect('TG N100/P250 Ron max SS 125 C', r[(100, 250, 'SS', 125)], 62.2, 2.0, 'ohm')


def run_array():
    r = array_path.main()
    expect_max('array on-current error (max)', max(v['on_err'] for v in r.values()), 0.05, '%')
    expect_max('array |dVt| at 27 C (max)', max(abs(v['dvt']) for k, v in r.items() if k[4] == 27), 0.02, 'mV')
    expect_max('array |dVt| 125 C after open subtraction (max)',
               max(abs(v['dvt_cor']) for v in r.values() if 'dvt_cor' in v), 0.06, 'mV')


def run_kelvin():
    r = array_kelvin.main()
    expect_max('array per-cell drain sense: R_tot error (max)', max(abs(v) for k, v in r.items() if k[1] == 'cell'), 0.01, '%')
    expect('array column-end sense: R_tot error, 10 um line', -r[(10.0, 'column', 0.1)], 1.1, 0.2, '%')


def run_post():
    r = array_post.main()
    expect('array after layout: R_tot error W9/L0.6, typ path', r[(9, 0.6, 0.1, 'TT', 27)]['typ']['r_err'], 0.16, 0.03, '%')
    expect_max('array after layout: on-current error after the table (max)',
               max(v['corrected']['on_err'] for v in r.values()), 0.10, '%')
    expect_max('array after layout: |dVt| at 27 C (max)',
               max(abs(x['dvt']) for k, v in r.items() if k[4] == 27 for x in v.values()), 0.02, 'mV')
    expect_max('array after layout: |dVt| 125 C after open subtraction (max)',
               max(abs(x['dvt_cor']) for v in r.values() for x in v.values() if 'dvt_cor' in x), 0.06, 'mV')


def run_cbcm():
    r = cbcm.main()
    expect('CBCM 300 fF error', 100 * (r[('acc', 300e-15)] / 300e-15 - 1), 1.2, 0.6, '%')
    expect('CBCM 1 pF error', 100 * (r[('acc', 1e-12)] / 1e-12 - 1), 0.3, 0.4, '%')
    expect_max('CBCM change with PADR (max)', max(abs(v) for k, v in r.items() if k[0] == 'pad'), 0.4, '%p')
    expect_max('CBCM C-V vs model Cgg + overlap, 1.5-5 V (max)',
               max(abs(100 * (a / b - 1)) for v, a, b in r['cv'] if v > 1.5), 1.0, '%')


def run_cbcm_block():
    r = cbcm_block.main()
    c, t = r[('acc', 2)]
    expect('CBCM block cell 2 (MET1-field) error', 100 * (c / t - 1), 1.49, 0.3, '%')
    c, t = r[('acc', 8)]
    expect('CBCM block cell 8 (gate W48/L10.5) error', 100 * (c / t - 1), 0.21, 0.2, '%')
    expect_max('CBCM block empty cell |C|', abs(r[('acc', 0)][0]) * 1e15, 0.05, 'fF')
    expect_min('CBCM block non-overlap at the gates (min)', r['gap_min'] * 1e9, 0.2, 'ns')
    expect_max('CBCM block unselected cells, cell 2', abs(r['others']), 0.01, '%')
    expect_max('CBCM block change with PADR (max)', max(abs(r[('pad', i)]) for i in (2, 8)), 0.4, '%p')
    expect_max('CBCM block C-V vs model Q/V, 1.5-5 V (max)',
               max(abs(100 * (c / t - 1)) for v, c, t in r['cv']), 1.0, '%')
    expect_max('CBCM block idle supply current (max)', max(abs(x) for x in r['idle']) * 1e12, 1.0, 'pA')


def run_cbcm_post():
    r = cbcm_post.main()
    expect_max('CBCM after layout: empty cell |C|', abs(r[('acc', 0)][0]) * 1e15, 0.05, 'fF')
    c, e = r[('acc', 2)]
    expect('CBCM after layout: cell 2 (MET1-field) error', 100 * (c / e - 1), 1.47, 0.3, '%')
    c, e = r[('acc', 8)]
    expect('CBCM after layout: cell 8 (gate W48/L10.5) error', 100 * (c / e - 1), 0.22, 0.2, '%')
    expect_min('CBCM after layout: non-overlap at the gates (min)', r['gap_min'] * 1e9, 0.35, 'ns')
    expect_max('CBCM after layout: cell 2 error spread, corners/VDD/clock', r['err2_span'], 0.5, '%p')
    expect_max('CBCM after layout: change with PADR (max)', max(abs(r[('pad', i)]) for i in (2, 8)), 0.4, '%p')
    expect_max('CBCM after layout: C-V cells 6-9, 1.5-5 V (max)',
               max(abs(100 * (c / e - 1)) for rows in r['cv'].values() for v, c, e in rows), 1.5, '%')


def run_ro():
    r = ro_bank.main()
    for k, f in (('inv', 123.1), ('nand', 93.8), ('nor', 66.8), ('fo4', 52.8), ('wire', 65.0), ('res', 69.1)):
        expect(f'RO {k} TT 27 C', r[k]['f27'] / 1e6, f, 0.02 * f, 'MHz')


def run_ro_post():
    r = ro_post.main()
    for k, f in (('inv', 121.8), ('nand', 93.1), ('nor', 66.4), ('wire', 64.6)):
        expect(f'RO bank {k}, plan loads + tap, TT 27 C', r[k]['block'] / 1e6, f, 0.02 * f, 'MHz')
    for k, f in (('inv', 99.2), ('nand', 83.2), ('nor', 60.6), ('wire', 55.9)):
        expect(f'RO bank {k}, drawn wiring, TT 27 C', r[k]['layout'] / 1e6, f, 0.02 * f, 'MHz')


def run_scan():
    r = scan_divider.main()
    expect('scan + decoder cases passing', r['scan_ok'], r['scan_n'], 0)
    expect('divider cases exactly /16', r['div_ok'], r['div_n'], 0)


def run_pnp():
    r = pnp_thermo.main()
    expect_max('PNP 3-current error 27-125 C (max |e|)', max(abs(v[0]) for v in r.values()), 0.2, 'K')


def run_lsplit():
    r = lsplit.main()
    expect('L-split Idsat W9/L0.6', r[('idsat', 0.6)] * 1e3, 4.56, 0.05, 'mA')
    expect('Terada-Muta R_sd 27 C', r[('tm', 27)][1], 120.8, 3, 'ohm')
    expect('Terada-Muta R_sd 125 C', r[('tm', 125)][1], 135.1, 3, 'ohm')


STEPS = dict(tg=run_tg, array=run_array, kelvin=run_kelvin, post=run_post, cbcm=run_cbcm, cbcm_block=run_cbcm_block,
             cbcm_post=run_cbcm_post, ro=run_ro, ro_post=run_ro_post, scan=run_scan, pnp=run_pnp, lsplit=run_lsplit)
OPTIONAL = {'post': array_post.KELVIN_R, 'cbcm_post': cbcm_post.CJSON,      # default only when their input exists
            'ro_post': ro_post.GDS}


def main():
    names = sys.argv[1:] or [n for n in STEPS if n not in OPTIONAL or os.path.exists(OPTIONAL[n])]
    for n in names:
        t = time.time()
        print(f"\n== {n}", flush=True)
        STEPS[n]()
        print(f"   ({time.time() - t:.0f} s)", flush=True)
    print('\n== summary')
    for name, v, ref, tol, unit, good in ROWS:
        lim = f"<= {ref:g}" if tol is None else f">= {ref:g}" if tol == 'min' else f"{ref:g} +/- {tol:g}"
        print(f"{'ok   ' if good else 'CHECK'} {name:48s} {v:10.4g} {unit:4s} (plan {lim})")
    bad = sum(1 for r in ROWS if not r[5])
    print(f"BLOCK CHECKS: {len(ROWS) - bad} ok, {bad} to check")


if __name__ == '__main__':
    main()
