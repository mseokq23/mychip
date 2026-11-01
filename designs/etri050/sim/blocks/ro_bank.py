"""Ring-oscillator bank: six 31-stage ROs from kit standard cells (5 corners at 27 C, TT at 125 C).

Stage 0 of every RO is NAND2X1 with the enable input, which is held low for 20 ns before
the start (with a free start the NAND RO can lock into its third harmonic).
Kinds: inv (INVX1), nand (NAND2X1), nor (NOR2X1), fo4 (INVX1 + 3 INVX1 loads),
wire (INVX1 + 300 um MET1 as 43.5 fF), res (INVX1 + poly2 40 squares with the PDK TC).
5 fF of local wiring per node. Frequency from rise 6 to 16 of one node; power = VDD x I_avg.
"""
from concurrent.futures import ProcessPoolExecutor
import os

from simlib import header, p2res, run

N = 31
KINDS = ['inv', 'nand', 'nor', 'fo4', 'wire', 'res']
CORNERS = ['TT', 'SS', 'FF', 'SF', 'FS']


def load(kind, i, y):
    s = ''
    if kind == 'fo4':
        s += ''.join(f"xl{i}_{j} {y} dl{i}_{j} vdd 0 INVX1\n" for j in range(3))
    elif kind == 'wire':
        # 300 um x 0.8 um MET1: 0.0435 fF/um2 x 240 um2 + 0.0551 fF/um x 600 um (design rules 5.5)
        s += f"cw{i} {y} 0 43.5f\n"
    return s + f"cp{i} {y} 0 5f\n"


def stage(kind, i, a, y, temp):
    if i == 0:
        return f"xs{i} {a} en {y} vdd 0 NAND2X1\n" + load(kind, i, y)
    if kind == 'nand':
        return f"xs{i} {a} vdd {y} vdd 0 NAND2X1\n" + load(kind, i, y)
    if kind == 'nor':
        return f"xs{i} {a} 0 {y} vdd 0 NOR2X1\n" + load(kind, i, y)
    if kind == 'res':
        return f"xs{i} {a} m{i} vdd 0 INVX1\nr{i} m{i} {y} {p2res(temp, 40):.1f}\n" + load(kind, i, y)
    return f"xs{i} {a} {y} vdd 0 INVX1\n" + load(kind, i, y)


def ro(args):
    kind, corner, temp, vdd = args
    net = header(corner, temp) + f"vdd vdd 0 {vdd}\nven en 0 pwl(0 0 20n 0 20.5n {vdd})\n"
    for i in range(N):
        net += stage(kind, i, f"n{(i - 1) % N}", f"n{i}", temp)
    tstop = 900e-9 if kind in ('res', 'wire', 'fo4', 'nor') else 400e-9
    net += f""".control
set noaskquit
tran 0.05n {tstop}
meas tran t1 when v(n5)={vdd / 2} rise=6
meas tran t2 when v(n5)={vdd / 2} rise=16
let f = 10 / (t2 - t1)
meas tran iavg avg i(vdd) from=t1 to=t2
let p = -iavg * {vdd}
echo "RES f=$&f p=$&p"
quit
.endc
.end
"""
    r = run(net, f"ro_{kind}_{corner}_{temp}_{vdd}")
    return r.get('f', float('nan')), r.get('p', float('nan'))


def main():
    # every corner at 27 C (corner ratios) and TT at 125 C (temperature coefficient)
    jobs = [(k, c, 27, 5.0) for k in KINDS for c in CORNERS] + [(k, 'TT', 125, 5.0) for k in KINDS]
    jobs += [('inv', 'TT', 27, 4.5), ('inv', 'TT', 27, 5.5)]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        res = dict(zip(jobs, ex.map(ro, jobs)))
    print(f"{'RO':5s} {'27C MHz':>8s} {'125C MHz':>9s} {'%/K':>7s} {'SS/TT':>6s} {'FF/TT':>6s} {'SF/TT':>6s} {'FS/TT':>6s} {'mW':>5s}")
    out = {}
    for k in KINDS:
        f27, p27 = res[(k, 'TT', 27, 5.0)]
        f125 = res[(k, 'TT', 125, 5.0)][0]
        tc = 100 * (f125 / f27 - 1) / 98
        ratios = [res[(k, c, 27, 5.0)][0] / f27 for c in ('SS', 'FF', 'SF', 'FS')]
        out[k] = dict(f27=f27, f125=f125, tc=tc, ratios=ratios, p=p27,
                      corners={c: res[(k, c, 27, 5.0)][0] for c in CORNERS})
        print(f"{k:5s} {f27 / 1e6:8.1f} {f125 / 1e6:9.1f} {tc:7.3f} " + ' '.join(f"{x:6.3f}" for x in ratios) + f" {p27 * 1e3:5.1f}")
    base = out['nand']['corners']['TT'] / out['nor']['corners']['TT']
    for c in ('SS', 'FF', 'SF', 'FS'):
        r = out['nand']['corners'][c] / out['nor']['corners'][c]
        print(f"NAND/NOR ratio {c}: {100 * (r / base - 1):+.1f} % vs TT ({base:.3f})")
    for c in ('SS', 'FF', 'SF', 'FS'):
        r = out['res']['corners'][c] / out['inv']['corners'][c]
        b = out['res']['corners']['TT'] / out['inv']['corners']['TT']
        print(f"RES/INV ratio {c}: {100 * (r / b - 1):+.1f} % vs TT")
    f45, f55 = res[('inv', 'TT', 27, 4.5)][0], res[('inv', 'TT', 27, 5.5)][0]
    print(f"INV RO VDD 4.5 / 5.0 / 5.5 V: {f45 / 1e6:.1f} / {out['inv']['f27'] / 1e6:.1f} / {f55 / 1e6:.1f} MHz")
    out['vdd'] = (f45, out['inv']['f27'], f55)
    return out


if __name__ == '__main__':
    main()
