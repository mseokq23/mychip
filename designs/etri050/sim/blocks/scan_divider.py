"""Transistor-level check of the scan path and the RO divider with kit standard cells.

scan     8-bit DFFPOSX1 shift register + shadow register (clocked by SLE through BUFX2) +
         3-to-8 decoder (NAND3X1 + INVX1); a pattern is shifted in, latched and decoded
         at SS/125 C/4.5 V, TT/27 C/5 V and FF/27 C/5.5 V, 1 and 10 MHz
divider  DFFPOSX1 + INVX1 toggle stages (4 stages, /16) at 100, 150, 200 MHz input
         (the fastest RO is about 132 MHz at FF/27 C)
"""
from concurrent.futures import ProcessPoolExecutor
import os

from simlib import header, run

N = 8
PAT = [1, 0, 1, 1, 0, 0, 1, 0]
PVT = [('SS', 125, 4.5), ('TT', 27, 5.0), ('FF', 27, 5.5)]


def scan_net(corner, temp, vdd, fclk):
    per = 1.0 / fclk
    n = header(corner, temp) + f"vdd vdd 0 {vdd}\n"
    n += f"vsck sck 0 pulse(0 {vdd} {per / 2:.4e} 1n 1n {per / 2 - 1e-9:.4e} {per:.4e} {N})\n"
    pts = "0 0"
    for k, b in enumerate(PAT):
        t = k * per
        pts += f" {t + 1e-9:.4e} {vdd * b} {t + per - 1e-9:.4e} {vdd * b}"
    n += f"vsdi sdi 0 pwl({pts})\n"
    tle = (N + 0.5) * per
    n += f"vsle sle 0 pwl(0 0 {tle:.4e} 0 {tle + 1e-9:.4e} {vdd} {tle + per / 2:.4e} {vdd} {tle + per / 2 + 1e-9:.4e} 0)\n"
    n += "xbc sck sckb vdd 0 BUFX2\nxbl sle sleb vdd 0 BUFX2\n"
    prev = 'sdi'
    for i in range(N):
        n += f"xs{i} {prev} sckb q{i} vdd 0 DFFPOSX1\nxh{i} q{i} sleb h{i} vdd 0 DFFPOSX1\n"
        prev = f"q{i}"
    n += "xi0 h0 h0b vdd 0 INVX1\nxi1 h1 h1b vdd 0 INVX1\nxi2 h2 h2b vdd 0 INVX1\n"
    for code in range(8):
        a = ['h0' if code & 1 else 'h0b', 'h1' if code & 2 else 'h1b', 'h2' if code & 4 else 'h2b']
        n += f"xd{code} {a[0]} {a[1]} {a[2]} dn{code} vdd 0 NAND3X1\nxe{code} dn{code} row{code} vdd 0 INVX1\n"
    tend = (N + 2) * per
    n += f".control\nset noaskquit\ntran {per / 200:.4e} {tend:.4e}\n"
    for i in range(N):
        n += f"meas tran vh{i} find v(h{i}) at={tend:.4e}\n"
    for code in range(8):
        n += f"meas tran vr{code} find v(row{code}) at={tend:.4e}\n"
    n += 'echo "RES ' + ' '.join([f"h{i}=$&vh{i}" for i in range(N)] + [f"r{c}=$&vr{c}" for c in range(8)])
    n += '"\nquit\n.endc\n.end\n'
    return n


def scan(args):
    corner, temp, vdd, f = args
    r = run(scan_net(corner, temp, vdd, f), f"scan_{corner}_{temp}_{f:.0f}")
    bits = ''.join('1' if r.get(f'h{i}', 0) > vdd / 2 else '0' for i in range(N))
    rows = [c for c in range(8) if r.get(f'r{c}', 0) > vdd / 2]
    return bits, rows


def div_net(corner, temp, vdd, fin, nst=4):
    per = 1 / fin
    n = header(corner, temp) + f"vdd vdd 0 {vdd}\nvck c0 0 pulse(0 {vdd} 1n 0.3n 0.3n {per / 2 - 0.3e-9:.4e} {per:.4e})\n"
    for i in range(nst):
        n += f"xf{i} d{i} c{i} q{i} vdd 0 DFFPOSX1\nxn{i} q{i} d{i} vdd 0 INVX1\nxb{i} q{i} c{i + 1} vdd 0 INVX1\n"
    tend = 64 * per + 5e-9
    n += f""".control
set noaskquit
tran {per / 100:.4e} {tend:.4e}
meas tran t1 when v(q{nst - 1})={vdd / 2} rise=1
meas tran t2 when v(q{nst - 1})={vdd / 2} rise=3
let ratio = {fin} * (t2 - t1) / 2
echo "RES ratio=$&ratio"
quit
.endc
.end
"""
    return n


def divider(args):
    corner, temp, vdd, fin = args
    return run(div_net(corner, temp, vdd, fin), f"div_{corner}_{temp}_{fin:.0f}").get('ratio', float('nan'))


def main():
    expect = ''.join(str(b) for b in reversed(PAT))
    code = int(expect[2]) * 4 + int(expect[1]) * 2 + int(expect[0])
    sjobs = [(c, t, v, f) for (c, t, v) in PVT for f in (1e6, 10e6)]
    djobs = [(c, t, v, f) for (c, t, v) in PVT for f in (100e6, 150e6, 200e6)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        sres = list(ex.map(scan, sjobs))
        dres = list(ex.map(divider, djobs))
    ok_scan = 0
    for (c, t, v, f), (bits, rows) in zip(sjobs, sres):
        good = bits == expect and rows == [code]
        ok_scan += good
        print(f"scan    {c} {t:3d} C {v} V {f / 1e6:4.0f} MHz: latched {bits} (expect {expect}), rows {rows} (expect [{code}]) {'OK' if good else 'FAIL'}")
    ok_div = 0
    for (c, t, v, f), ratio in zip(djobs, dres):
        good = abs(ratio - 16) < 0.01
        ok_div += good
        print(f"divider {c} {t:3d} C {v} V {f / 1e6:4.0f} MHz: ratio {ratio:.3f} {'OK' if good else 'FAIL'}")
    return dict(scan_ok=ok_scan, scan_n=len(sjobs), div_ok=ok_div, div_n=len(djobs))


if __name__ == '__main__':
    main()
