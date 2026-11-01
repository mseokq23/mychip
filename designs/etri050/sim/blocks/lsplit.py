"""L-split NMOS (W 9 um): saturation current of the direct devices and a Terada-Muta
extraction on L = 0.6, 1.2, 3, 9 um (the array's W 9 um columns) at 27 and 125 C.

R_tot(L) = VDS / ID at VDS = 0.1 V for VGS = 3, 4, 5 V; the lines meet at (dL, R_sd).
The model card value RDSW / W_eff is printed for comparison.
"""
import re

import numpy as np

from simlib import BUILD, geo, header, run

W = 9
LS = [0.6, 1.2, 3, 9]


def idrain(w, l, vgs, vds, temp):
    net = header('TT', temp) + f"""m1 d g 0 0 nmos4 w={w}u l={l}u {geo(w, 1.8)}
vd d 0 {vds}
vg g 0 {vgs}
.control
op
let id = -i(vd)
echo "RES id=$&id"
.endc
.end
"""
    return run(net, f"ls_{w}_{l}_{vgs}_{vds}_{temp}")['id']


def model_rds(temp):
    txt = open(f"{BUILD}/05cmos_mosfet_corner.lib").read()
    sect = txt[txt.index('.LIB MOS'):]

    def par(name):
        return float(re.search(r'\b%s\s*=\s*([-+0-9.Ee]+)' % name, sect).group(1))
    rdsw, prt, wint = par('RDSW'), par('PRT'), par('WINT')
    t, tn = temp + 273.15, 27 + 273.15
    return (rdsw + prt * (t / tn - 1)) / (W - 2 * wint * 1e6)


def main():
    out = {}
    for l in (0.6, 1.2):
        i = idrain(W, l, 5, 4.5, 27)
        print(f"Idsat W {W}/L {l}: {i * 1e3:.2f} mA, {i * 4.5e3:.1f} mW at VGS 5 V, VDS 4.5 V, 27 C")
        out[('idsat', l)] = i
    for temp in (27, 125):
        lines = []
        for vgs in (3, 4, 5):
            r = [0.1 / idrain(W, l, vgs, 0.1, temp) for l in LS]
            m, b = np.polyfit(LS, r, 1)
            lines.append((m, b))
            out[('line', temp, vgs)] = (m, b)
            print(f"T={temp:3d} C VGS {vgs}: R_tot {np.round(r, 1)} ohm, slope {m:6.1f} ohm/um, intercept {b:6.1f} ohm")
        pts = []
        for a in range(3):
            for c in range(a + 1, 3):
                (m1, b1), (m2, b2) = lines[a], lines[c]
                x = (b2 - b1) / (m1 - m2)
                pts.append((x, m1 * x + b1))
        x, y = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
        out[('tm', temp)] = (-x, y)
        print(f"T={temp:3d} C Terada-Muta: dL {-x:.3f} um, R_sd {y:.1f} ohm (model card RDSW/W_eff {model_rds(temp):.1f} ohm, before PRWG)")
    (m27, b27), (m125, b125) = out[('line', 27, 5)], out[('line', 125, 5)]
    print(f"27 -> 125 C at VGS 5 V: slope {100 * (m125 / m27 - 1):+.0f} %, intercept {100 * (b125 / b27 - 1):+.0f} %")
    return out


if __name__ == '__main__':
    main()
