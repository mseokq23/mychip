"""The PDK models against ETRI's process monitor (TEG) results of the 2026-1 MPW, and the chip's expected
values with those results.

ETRI shared the TEG results of the 2026-1 MPW in its answer to our question 6 (MyChip QnA, 2026-11-06,
"for comparison of designs and measurements"; the reply is public on MoaFab's board,
https://www.moafab.kr/css/board/myChip_qna/read?BOARD_SKEY=1311): MOSFETs W/L = 20/0.5 um, sheet
resistances averaged, contact and via resistance from string patterns; no oxide thickness or dL / dW data.

  1. MOSFET W/L = 20/0.5 um at 25 C in the five corners: threshold voltage by two common definitions
     (constant current 0.1 uA x W/L at |VDS| 0.1 V, and the maximum-gm linear extrapolation at |VDS|
     0.1 V minus VDS/2) and the saturation current per um of width at |VGS| = |VDS| = 5 V. ETRI does not
     say which definition its TEG uses, so both are given; neither puts the TT model on the design target
     for both devices (PMOS by constant current is 108 mV off, outside +-0.10 V).
  2. The chip's poly2 structures with the measured sheet and contact resistance: the heater (6 squares,
     16 contacts at each end) and the resistor ring oscillator (ro_post.py, the drawn wiring: needs
     designs/etri050/ro/build/rores_full.gds, from run_chip.sh or etri050_ro.py --block rores; left out
     with a note when it is not there).

usage: python3 pcm_compare.py      (about 15 s; writes build/pcm_compare.txt)
"""
import os

import numpy as np

from simlib import BUILD, geo, header, p2res, run

# ETRI, MyChip QnA answer to question 6 (2026-11-06): design rule target, 2026-1 MPW TEG result
TARGET = {"vtn": (0.70, 0.10), "idn": (550, 50), "vtp": (-0.90, 0.10), "idp": (-280, 30),
          "rsh_n": 65, "rsh_p": 180, "rsh_poly1": 50, "rsh_poly2": 125, "rc_poly2": 50, "via1": 2.0, "via2": 1.5}
MPW1 = {"vtn": (0.751, 0.03), "idn": (514, 24), "vtp": (-0.998, 0.02), "idp": (-266, 53),
        "rsh_n": 71.3, "rsh_p": 163.2, "rsh_poly1": 53.0, "rsh_poly2": 154.2, "rc_poly2": 57.6,
        "via1": 0.28, "via2": 0.29}
RULE_POLY2 = (110, 125, 140)             # rule document 5.2: poly2 sheet resistance min / typ / max
CORNERS = ("TT", "SS", "FF", "SF", "FS")
W, L, TEMP = 20.0, 0.5, 25


def mos(kind, corner):
    """Id-Vg at |VDS| = 0.1 V and the saturation current of one W/L = 20/0.5 transistor."""
    s = 1 if kind == "n" else -1
    dev = "nmos4" if kind == "n" else "pmos4"
    data = os.path.join(BUILD, f"pcm_{kind}_{corner}.dat")
    net = header(corner, TEMP) + f"""m1 d g 0 0 {dev} w={W}u l={L}u {geo(W)}
vd d 0 {s * 0.1}
vg g 0 0
.control
dc vg 0 {s * 5} {s * 0.005}
let id = {-s}*i(vd)
wrdata {data} id
alter vd {s * 5}
op
let isat = {-s}*i(vd)
alter vg {s * 5}
op
let isat = {-s}*i(vd)
echo "RES isat=$&isat"
.endc
.end
"""
    res = run(net, f"pcm_{kind}_{corner}")
    v, i = np.loadtxt(data, usecols=(0, 1), unpack=True)
    v = np.abs(v)
    vt_cc = float(np.interp(0.1e-6 * W / L, i, v))
    gm = np.gradient(i, v)
    k = int(np.argmax(gm))
    vt_gm = float(v[k] - i[k] / gm[k] - 0.1 / 2)
    return s * vt_cc, s * vt_gm, s * res["isat"] / W * 1e6


def ror(rsh):
    """The resistor RO's frequency (MHz) with its drawn wiring, TT 27 C, for a poly2 sheet resistance;
    None without the block's layout."""
    import ro_post
    if not os.path.exists(ro_post.RES_GDS):
        return None
    f = ro_post.job_res(("layout", "TT", 27, float(rsh), 1.0))[0]
    return f / 1e6


def main():
    rows, out = {}, []
    for c in CORNERS:
        rows[c] = (*mos("n", c), *mos("p", c))
    out.append(f"MOSFET W/L = {W:g}/{L:g} um, {TEMP} C (PDK corner models, ngspice)")
    out.append("  corner   NMOS Vt(cc)  Vt(gm)  Idsat uA/um   PMOS Vt(cc)  Vt(gm)  Idsat uA/um")
    for c in CORNERS:
        vn1, vn2, idn, vp1, vp2, idp = rows[c]
        out.append(f"  {c:6s}   {vn1:9.3f}  {vn2:6.3f}  {idn:9.0f}     {vp1:9.3f}  {vp2:6.3f}  {idp:9.0f}")
    out.append(f"  target   {TARGET['vtn'][0]:.2f} +- {TARGET['vtn'][1]:.2f}  {TARGET['idn'][0]} +- {TARGET['idn'][1]}"
               f"        {TARGET['vtp'][0]:.2f} +- {TARGET['vtp'][1]:.2f}  {TARGET['idp'][0]} +- {TARGET['idp'][1]}")
    out.append(f"  2026-1   {MPW1['vtn'][0]:.3f} +- {MPW1['vtn'][1]:.2f}  {MPW1['idn'][0]} +- {MPW1['idn'][1]}"
               f"        {MPW1['vtp'][0]:.3f} +- {MPW1['vtp'][1]:.2f}  {MPW1['idp'][0]} +- {MPW1['idp'][1]}")
    tt = rows["TT"]
    for name, j in (("Vt(cc)", 0), ("Vt(gm)", 1)):
        out.append(f"  TT model vs target, {name}: NMOS {tt[j] - TARGET['vtn'][0]:+.3f} V, "
                   f"PMOS {tt[j + 3] - TARGET['vtp'][0]:+.3f} V")
    # where the 2026-1 silicon sits: the fraction of the way from TT to SS for each quantity
    for name, j, key in (("NMOS Vt(cc)", 0, "vtn"), ("NMOS Vt(gm)", 1, "vtn"), ("NMOS Idsat", 2, "idn"),
                         ("PMOS Vt(cc)", 3, "vtp"), ("PMOS Vt(gm)", 4, "vtp"), ("PMOS Idsat", 5, "idp")):
        a, b = rows["TT"][j], rows["SS"][j]
        out.append(f"  2026-1 {name}: {MPW1[key][0]:g} = TT + {(MPW1[key][0] - a) / (b - a):.2f} x (SS - TT)")
    # poly2: the heater and the resistor RO
    out.append("poly2 (rule document 5.2: 110 / 125 / 140 ohm/sq; 2026-1 MPW 154.2 ohm/sq, contact 57.6 ohm)")
    for label, rsh, rc in (("rule min", RULE_POLY2[0], 40.0), ("rule typ", RULE_POLY2[1], 50.0),
                           ("rule max", RULE_POLY2[2], 60.0), ("2026-1 MPW", MPW1["rsh_poly2"], MPW1["rc_poly2"])):
        r25 = p2res(25, 6, rsh) + 2 * rc / 16
        r115 = p2res(115, 6, rsh) + 2 * rc / 16
        out.append(f"  heater {label:10s}: {r25:6.0f} ohm at 25 C ({r115:6.0f} at 115 C); at 5 V {5 / r25 * 1e3:4.2f} mA, "
                   f"{25 / r25 * 1e3:4.1f} mW; at 5 mA {5e-3 * r25:4.2f} V, {25e-6 * r25 * 1e3:4.1f} mW")
    for label, rsh in (("rule typ", 125.0), ("2026-1 MPW", MPW1["rsh_poly2"])):
        f = ror(rsh)
        out.append(f"  resistor RO, drawn wiring, TT 27 C, {label} ({rsh:g} ohm/sq): " +
                   (f"{f:.1f} MHz" if f is not None else "no layout (designs/etri050/ro/build/rores_full.gds: "
                    "run_chip.sh or etri050_ro.py --block rores)"))
    text = "\n".join(out)
    open(os.path.join(BUILD, "pcm_compare.txt"), "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
