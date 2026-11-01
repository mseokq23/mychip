"""Die thermometer: PDK vertical PNP (pnp10, emitter 10 x 10 um) read through the PANA
series resistor (PADR, ~725 ohm), base = collector = VSS.

Three-current method (1, 3, 9 uA): two differences cancel the linear series term
  a = dV(1->3) - R * 2 uA, R = (dV(3->9) - dV(1->3)) / 4 uA, a = n k T / q * ln 3
with n calibrated at 27 C. The two-current estimate (no series correction, also calibrated
at 27 C) is printed for comparison.
"""
import math

from simlib import run

K = 8.617333262e-5
TEMPS = [27, 60, 85, 125]
CURRENTS = ['1u', '3u', '9u']


def measure():
    net = """* pnp10 through PADR
.lib '05cmos_model_260210.lib' BJT
.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9
ie 0 pad 1u
rpadr pad e 725
q1 0 0 e pnp10
.control
set noaskquit
"""
    for t in TEMPS:
        for i in CURRENTS:
            net += f"option temp = {t}\nalter ie dc = {i}\nop\nlet v = v(pad)\necho \"RES v{t}_{i}=$&v\"\n"
    net += "quit\n.endc\n.end\n"
    r = run(net, 'pnp_thermo')
    return {t: [r[f"v{t}_{i}"] for i in CURRENTS] for t in TEMPS}


def main():
    v = measure()
    res = {}
    for t in TEMPS:
        v1, v3, v9 = v[t]
        d12, d23 = v3 - v1, v9 - v3
        rs = (d23 - d12) / 4e-6
        res[t] = (d12 - rs * 2e-6, d12, rs)
    t0 = 27 + 273.15
    n3 = res[27][0] / (K * t0 * math.log(3))
    n2 = res[27][1] / (K * t0 * math.log(3))
    out = {}
    for t in TEMPS:
        a, a2, rs = res[t]
        e3 = a / (n3 * K * math.log(3)) - 273.15 - t
        e2 = a2 / (n2 * K * math.log(3)) - 273.15 - t
        out[t] = (e3, e2)
        print(f"T={t:3d} C  series R fit {rs:6.1f} ohm  3-current error {e3:+.2f} K  2-current error {e2:+.2f} K")
    dvdt = (v[125][1] - v[27][1]) / 98 * 1e3
    print(f"dV/dT at 3 uA (incl. PADR drop): {dvdt:.2f} mV/K")
    return out


if __name__ == '__main__':
    main()
