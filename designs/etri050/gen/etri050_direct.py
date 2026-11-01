#!/usr/bin/env python3
"""Direct-access reference devices of pdkv, generated from code and drawn by Magic.

  lsplit  two NMOS, W 9 um, L 0.6 and 1.2 um, sharing gate and source (same geometry as array
          columns 0 and 1). Every drain and the source get two exits: force (metal2, top) and
          sense (metal2, bottom), split right at the contact strip (Kelvin).
  mosc    N-well MOS capacitor: four P-channel gates of 99.9 x 99.9 um (2 x 2, about 118 pF in
          total), p+ source/drain strips on both sides supply the inversion layer, n+ well taps
          between the pieces (every gate point within 54 um of a tap; rule <= 60 um).
          LO = N-well with the p+ strips, HI = gate.

Geometry is worked out on Magic's lambda grid (0.3 um, half-lambda allowed) like etri050_mos.py:
Magic draws the cell in batch mode with the kit technology, so cuts, implants and wells come out
of the kit's ETRI GDS style. Each cell gets a schematic netlist for LVS. Ports are the nets once:
the sense stubs of lsplit belong to the force nets and carry no port of their own (LVS cannot
tell two ports of one net apart); the chip routes them to the sense pads.

  python3 designs/etri050/gen/etri050_direct.py                 # both cells into designs/etri050/direct/build
  python3 designs/etri050/gen/etri050_direct.py lsplit --check  # Magic DRC, KLayout DRC, LVS (etri-check)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etri050_mos import LAMBDA_UM, REPO, etri_check, run_magic, um  # noqa: E402

DEFAULT_OUT = REPO / "designs/etri050/direct/build"
VIA = 7          # m2contact tile (0.9 um cut with 0.6 um border = 2.1 um), as the kit LEF via
CONTACT = 6      # diffusion / poly contact tile (one 0.6 um cut with 0.6 um border)
M2W = 4          # metal2 stub width 1.2 um (official 10.MET2.W 1.0 um)


class Cell:
    def __init__(self, name: str):
        self.name = name
        self.rects: list[tuple[str, float, float, float, float]] = []
        self.ports: list[tuple[str, str, float, float, float, float]] = []

    def paint(self, layer, x0, y0, x1, y1):
        self.rects.append((layer, x0, y0, x1, y1))

    def port(self, name, layer, x0, y0, x1, y1):
        self.ports.append((name, layer, x0, y0, x1, y1))

    def bbox(self):
        xs = [v for r in self.rects for v in (r[1], r[3])]
        ys = [v for r in self.rects for v in (r[2], r[4])]
        return min(xs), min(ys), max(xs), max(ys)

    def magic_tcl(self) -> str:
        out = [f"load {self.name}"]
        for layer, x0, y0, x1, y1 in self.rects:
            out += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"paint {layer}"]
        for name, layer, x0, y0, x1, y1 in self.ports:      # ports 1..n in this order
            out += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"label {name} c {layer}"]
        bx0, by0, bx1, by1 = self.bbox()
        out += [f"box {um(bx0 - 1)} {um(by0 - 1)} {um(bx1 + 1)} {um(by1 + 1)}", "port makeall",
                f"save {self.name}"]
        return "\n".join(out) + "\n"


def lsplit(w_um=9.0, l1_um=0.6, l2_um=1.2) -> tuple[Cell, str]:
    w, l1, l2 = (round(v / LAMBDA_UM) for v in (w_um, l1_um, l2_um))
    gap, cap = 2, 2                      # contact strip to gate, poly beyond active
    c = Cell("lsplit")
    xd1 = 0
    xg1 = xd1 + CONTACT + gap
    xs = xg1 + l1 + gap
    xg2 = xs + CONTACT + gap
    xd2 = xg2 + l2 + gap
    xact = xd2 + CONTACT
    c.paint("ndiffusion", 0, 0, xact, w)
    for x in (xd1, xs, xd2):
        c.paint("ndcontact", x, 0, x + CONTACT, w)
    top = w + 30                          # cell top: force and gate exits end here
    bot = -30                             # cell bottom: sense exits end here
    # gates: up to a poly bar 2 lambda above the active, gate contact at its left end
    pbar0, pbar1 = w + 2, w + 5
    c.paint("polysilicon", xg1, -cap, xg1 + l1, pbar1)
    c.paint("polysilicon", xg2, -cap, xg2 + l2, pbar1)
    c.paint("polysilicon", -10, pbar0, xg2 + l2, pbar1)
    c.paint("polycontact", -10, w + 1, -10 + CONTACT, w + 1 + CONTACT)
    c.paint("metal1", -10, w + 1 + CONTACT, -10 + CONTACT, top)
    c.port("LG", "metal1", -10, top - 4, -10 + CONTACT, top)
    # force exits (top) and sense stubs (bottom) from every strip, through via1 to metal2
    names = {xd1: "LD1F", xs: "LSF", xd2: "LD2F"}
    for x, name in names.items():
        cx = x + CONTACT / 2
        vx0, vx1 = cx - VIA / 2, cx + VIA / 2
        c.paint("metal1", x, w, x + CONTACT, w + 9)
        c.paint("m2contact", vx0, w + 9, vx1, w + 9 + VIA)
        c.paint("metal2", cx - M2W / 2, w + 9, cx + M2W / 2, top)
        c.port(name, "metal2", cx - M2W / 2, top - 4, cx + M2W / 2, top)
        c.paint("metal1", x, -3, x + CONTACT, 0)
        c.paint("m2contact", vx0, -3 - VIA, vx1, -3)
        c.paint("metal2", cx - M2W / 2, bot, cx + M2W / 2, -3)
    # substrate tap below the sense vias (metal2 stubs cross it)
    c.paint("psubstratepcontact", -10, -22, xact + 4, -22 + CONTACT)
    c.port("VSS", "metal1", -10, -22, -10 + CONTACT, -22 + CONTACT)
    sch = (f"* lsplit: NMOS W {w_um:g} um, L {l1_um:g} and {l2_um:g} um, shared gate and source\n"
           ".subckt lsplit LG LD1F LSF LD2F VSS\n"
           f"M1 LD1F LG LSF VSS nfet W={w_um:g}u L={l1_um:g}u\n"
           f"M2 LD2F LG LSF VSS nfet W={w_um:g}u L={l2_um:g}u\n"
           ".ends\n")
    return c, sch


def mosc(side_um=99.9) -> tuple[Cell, str]:
    g = round(side_um / LAMBDA_UM)       # gate W = L (lambda)
    c = Cell("mosc")
    gap = 2
    pw = CONTACT + gap + g + gap + CONTACT          # piece active width
    px = pw + 4 + CONTACT + 4                       # piece pitch in x (shared n+ tap between)
    py = (g + 3 + CONTACT) + 6 + (3 + CONTACT)      # piece pitch in y
    for ix in range(2):
        for iy in range(2):
            x0, y0 = ix * px, iy * py
            c.paint("pdiffusion", x0, y0, x0 + pw, y0 + g)
            c.paint("pdcontact", x0, y0, x0 + CONTACT, y0 + g)
            c.paint("pdcontact", x0 + pw - CONTACT, y0, x0 + pw, y0 + g)
            gx0, gx1 = x0 + CONTACT + gap, x0 + CONTACT + gap + g
            c.paint("polysilicon", gx0, y0 - 3 - CONTACT, gx1, y0 + g + 3 + CONTACT)
            c.paint("polycontact", gx0 + 4, y0 + g + 3, gx1 - 4, y0 + g + 3 + CONTACT)
            c.paint("polycontact", gx0 + 4, y0 - 3 - CONTACT, gx1 - 4, y0 - 3)
    h = py + g                                      # top of the upper active row
    # n+ well taps: left, middle (shared), right; metal1 joins each tap with the p+ strips beside it
    taps = [-4 - CONTACT, pw + 4, px + pw + 4]
    for t in taps:
        c.paint("nsubstratencontact", t, 0, t + CONTACT, h)
    c.paint("metal1", taps[0], -20, CONTACT, h)                    # left tap + left p+ strip
    c.paint("metal1", pw - CONTACT, -20, px + CONTACT, h)          # middle: strip, tap, strip
    c.paint("metal1", px + pw - CONTACT, -20, taps[2] + CONTACT, h)
    c.paint("metal1", taps[0], -26, taps[2] + CONTACT, -20)        # LO bar below
    c.paint("nwell", taps[0] - 6, -6, taps[2] + CONTACT + 6, h + 6)
    # gate straps: one per column through the four contact rows, joined above
    for ix in range(2):
        cx = ix * px + pw / 2
        c.paint("metal1", cx - 5, -3 - CONTACT, cx + 5, h + 3 + CONTACT + 12)
    c.paint("metal1", pw / 2 - 5, h + 3 + CONTACT + 6, px + pw / 2 + 5, h + 3 + CONTACT + 12)
    c.port("CHI", "metal1", pw / 2 - 5, h + 3 + CONTACT + 6, px + pw / 2 + 5, h + 3 + CONTACT + 12)
    c.port("CLO", "metal1", taps[0], -26, taps[2] + CONTACT, -20)
    gu = g * LAMBDA_UM
    sch = (f"* mosc: N-well MOS capacitor, 4 P-channel gates {gu:.1f} x {gu:.1f} um\n"
           ".subckt mosc CHI CLO\n"
           + "".join(f"M{i} CLO CHI CLO CLO pfet W={gu:.1f}u L={gu:.1f}u\n" for i in range(1, 5))
           + ".ends\n")
    return c, sch


CELLS = {"lsplit": lsplit, "mosc": mosc}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cells", nargs="*", default=list(CELLS), help="lsplit, mosc (default: both)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="Magic DRC, ETRI GDS, KLayout DRC and LVS (etri-check)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sch").mkdir(exist_ok=True)
    bad = 0
    for name in args.cells:
        cell, sch = CELLS[name]()
        for ext in (".mag", ".ext", ".spice", ".gds"):
            (args.out / f"{name}{ext}").unlink(missing_ok=True)
        run_magic(cell.magic_tcl() + f"cif ostyle lambda=0.30(ETRI)\ngds write {name}.gds\n",
                  args.out, f"{name}_build.log")
        if not (args.out / f"{name}.gds").exists():
            sys.exit(f"Magic did not write {name}.gds (see {args.out / (name + '_build.log')})")
        (args.out / "sch" / f"{name}.spice").write_text(sch)
        x0, y0, x1, y1 = cell.bbox()
        print(f"{name}: {(x1 - x0) * LAMBDA_UM:.1f} x {(y1 - y0) * LAMBDA_UM:.1f} um, "
              f"ports {', '.join(p[0] for p in cell.ports)}")
        if args.check:
            ok, line = etri_check(name, str(args.out / "sch" / f"{name}.spice"), args.out)
            print("  " + line)
            bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
