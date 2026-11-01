"""Where the drain sense must tap the array column (Kelvin point).

One array column of 12 NMOS cells, the selected cell at the far end (worst case), column
force line as a resistor ladder (MET2, 40 um per row). Two options for the drain sense:

  column   one sense TG at the column end next to the force TG (sense taps the line there)
  cell     a sense TG in every cell, gated by the row select, onto a separate column sense
           line; only the selected cell's sense TG is on

Source side: common mesh with a sensed tap and 0.2 ohm unsensed (as in array_path.py).
Reported: R_tot = VDS / ID error against an ideal device at VGS = 5 V, VDS = 0.1 V
(linear region, what the R_sd extraction uses) and the current error at VDS = 4.5 V.
"""
from simlib import geo, header, run

NROW = 12
PITCH_UM = 40.0
MET2_RSH = 0.08          # ohm/sq, design rules 5.2 (typ)


def tgate(name, a, b, en, enb, wn, wp):
    return (f"mn{name} {a} {en} {b} 0 nmos4 w={wn}u l=0.6u {geo(wn)}\n"
            f"mp{name} {a} {enb} {b} vdd pmos4 w={wp}u l=0.6u {geo(wp)}\n")


def netlist(w, l, vds, sense, line_w_um, sel=NROW - 1, temp=27):
    rseg = PITCH_UM / line_w_um * MET2_RSH
    n = header('TT', temp) + "vdd vdd 0 5\n"
    n += f"vdset dset 0 {vds}\nedf dfo 0 dset pds 1e5\nvmd dfo pdf 0\n"
    n += "esf sfo 0 0 pss 1e5\nvms sfo psf 0\nvg g 0 5\n"
    n += "rdf pdf bdf 2\nrds pds bds 10\nrsf psf smesh 2\nrss pss sstap 10\nrsm sstap smesh 0.2\n"
    n += tgate('f', 'bdf', 'c0', 'vdd', '0', 100, 250)
    for k in range(NROW - 1):
        n += f"rc{k} c{k} c{k + 1} {rseg:.4f}\n"
    if sense == 'column':
        n += tgate('s', 'bds', 'c0', 'vdd', '0', 6, 15)
    else:
        n += tgate('s', 'bds', 'sl0', 'vdd', '0', 6, 15)
        for k in range(NROW - 1):
            n += f"rsl{k} sl{k} sl{k + 1} {rseg * 5:.4f}\n"       # narrow sense line, no current
        for k in range(NROW):
            on = (k == sel)
            n += tgate(f'c{k}', f'c{k}', f'sl{k}', 'vdd' if on else '0', '0' if on else 'vdd', 3, 7.5)
    for k in range(NROW):
        gate = 'g' if k == sel else '0'
        n += f"md{k} c{k} {gate} smesh 0 nmos4 w={w}u l={l}u {geo(w)}\n"
    n += f"vrd rd 0 {vds}\nmref rd g 0 0 nmos4 w={w}u l={l}u {geo(w)}\n"
    n += """.control
set noaskquit
op
let ia = i(vmd)
let ir = -i(vrd)
echo "RES ia=$&ia ir=$&ir"
quit
.endc
.end
"""
    return n


def main():
    out = {}
    for line_w in (6.0, 10.0):
        for sense in ('column', 'cell'):
            for vds in (0.1, 4.5):
                r = run(netlist(9, 0.6, vds, sense, line_w), f"kelvin_{sense}_{line_w:.0f}_{vds}")
                err = 100 * (r['ia'] / r['ir'] - 1)
                out[(line_w, sense, vds)] = err
                what = 'R_tot error' if vds < 1 else 'I error'
                val = -err if vds < 1 else err
                print(f"line {line_w:4.1f} um ({NROW * PITCH_UM / line_w * MET2_RSH:4.1f} ohm), sense at {sense:6s}: "
                      f"VDS {vds} V  {what} {val:+.3f} %  (I_ref {r['ir'] * 1e3:.3f} mA)", flush=True)
    return out


if __name__ == '__main__':
    main()
