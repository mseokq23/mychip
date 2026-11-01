"""Transmission-gate on-resistance over the full 0-5 V signal range.

Largest Ron over 0.05-4.95 V for the gate sizes considered for the array switches
(L = 0.6 um, VDD = 5 V): TT/SS corners at 27 and 125 C.
"""
from simlib import geo, header, run

SIZES = [(40, 40), (40, 100), (60, 150), (100, 250)]
LEVELS = [0.05, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 4.95]


def ron_max(wn, wp, corner, temp):
    net = header(corner, temp) + f"""vdd vdd 0 5
va a 0 1
vb b 0 0.99
mn a vdd b 0 nmos4 w={wn}u l=0.6u {geo(wn)}
mp a 0 b vdd pmos4 w={wp}u l=0.6u {geo(wp)}
.control
set noaskquit
"""
    for k, v in enumerate(LEVELS):
        net += f"alter va dc = {v}\nalter vb dc = {v - 0.01}\nop\nlet r = 0.01 / (-i(va))\necho \"RES r{k}=$&r\"\n"
    net += "quit\n.endc\n.end\n"
    r = run(net, f"tg_{wn}_{wp}_{corner}_{temp}")
    vals = [r[f"r{k}"] for k in range(len(LEVELS)) if f"r{k}" in r]
    return max(vals) if len(vals) == len(LEVELS) else float('nan')


def main():
    out = {}
    for wn, wp in SIZES:
        for corner, temp in (('TT', 27), ('SS', 125)):
            out[(wn, wp, corner, temp)] = ron_max(wn, wp, corner, temp)
            print(f"TG N{wn}/P{wp} {corner} {temp:3d} C: Ron_max = {out[(wn, wp, corner, temp)]:6.1f} ohm", flush=True)
    return out


if __name__ == '__main__':
    main()
