#!/usr/bin/env python3
"""Kelvin device array of pdkv (12 rows x 8 columns), generated from code and drawn by Magic.

Circuit (plan section "Kelvin 소자 어레이"; designs/etri050/sim/blocks/array_path.py and
array_kelvin.py simulate it):

  cell (r, c)   DUT: NMOS (rows 0-7) or PMOS (rows 8-11) with the geometry of column c, gate G<r>,
                source = the common source plate SRC, drain = the column force line D<c>;
                NMOS bulk VSS (substrate), PMOS bulk ANW (N-well of the PMOS rows).
                Drain-sense TG N 3 / P 7.5 um from the drain terminal to the column sense line
                DS<c>, gated by the row select (row_sel<r> / row_selb<r>); its PMOS in a VDD well.
                Column 7 is the open reference column: the same cell without the DUT, the TG
                tapping D<7> where the drain would be.
  row driver r  gate TG N 6 / P 15 um between AG and G<r> (row_sel<r> / row_selb<r>);
                parking: NMOS rows NMOS W 6 from G<r> to VSS (gate row_selb<r>), PMOS rows
                PMOS W 6 from G<r> to ANW (gate row_sel<r>, body VDD). The plan sizes them W 3;
                W 6 doubles the only gate of its type on a long select line (a PMOS row's
                row_sel has no other P gate, an NMOS row's row_selb no other N gate). In the
                chip, row_sel11's metal2 (bus to the top row) is 755 um2: 419x the W 3 gate,
                over the 400 of rule document 10.MET2.ANT when the ratio is taken per gate type
                over the finished net as ETRI's Calibre macro would (the rule is commented out
                there); 210x with W 6 (scripts/antenna_rules.py). A parking device is off in a
                selected row and only holds G<r> in the others.
  column c      force TG N 4 x 25.2 um / P 10 x 25.2 um (100.8 / 252 um, fingers <= 100 um)
                between ADF and D<c>; sense TG N 6 / P 15 um between ADS and DS<c>
                (col_sel<c> / col_selb<c>); parking TG N 3 / P 7.5 um from D<c> to SRC
                (col_selb<c> / col_sel<c>), so an unselected column has VDS = 0 for both
                device types (array_path.py parks the NMOS-only array with an NMOS).

Kelvin points: every drain is forced at the top end of its contact strip (via1 to D<c>) and
sensed at the bottom end (metal1 to the cell TG), as in the direct L-split cell; the source
plate (metal3) is sensed by ASS at its centre (chip routing).

Drawing: geometry on Magic's lambda grid (0.3 um, half lambda allowed), drawn by Magic in batch
mode with the kit technology like etri050_direct.py, so cuts, implants and wells come out of the
kit's ETRI GDS style. Metal2 and metal3 are at least 4 lambda (1.2 um) wide and 4 lambda apart
(rule document 10.MET2.S1, 12.MET3.S1: 1.0 um). N-wells keep 14 lambda (4.2 um) apart (1.NWL.S.2).

  python3 designs/etri050/gen/etri050_array.py [--out DIR] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etri050_mos import LAMBDA_UM, REPO, etri_check, run_magic, um  # noqa: E402

DEFAULT_OUT = REPO / "designs/etri050/array/build"
NAME = "karray"

# ---- technology constants (lambda) ---------------------------------------------------------------
CT = 6           # diffusion / poly / tap contact tile (one 0.6 um cut, 0.6 um border)
VIA = 7          # m2contact / m3contact tile (0.8 um cut, 0.6 um border; 2.1 um)
GAP = 2          # contact tile to gate
CAP = 2          # poly beyond active
MW = 4           # metal2 / metal3 signal width (1.2 um)
MS = 4           # metal2 / metal3 spacing (1.2 um >= 1.0 um)
LW = 4           # metal1 line width
WELL_S = 14      # N-well to N-well (4.2 um >= 4.0 um, different potential)

# ---- circuit (um) -------------------------------------------------------------------------------------
COLUMNS = [(9.0, 0.6), (9.0, 1.2), (9.0, 3.0), (3.0, 0.6), (3.0, 3.0), (9.0, 9.0), (18.0, 18.0), None]
N_NMOS_ROWS, N_PMOS_ROWS = 8, 4
# Physical order of the columns, left to right (column index = col_sel index of the control block).
# Mirrored so that the switch inputs follow the order of the control block's top-edge pins
# (col_selb<7..0> then col_sel<7..0>, left to right): 8 routing tracks under the array instead of 12.
PHYS = [7, 6, 5, 4, 3, 2, 1, 0]
NROWS, NCOLS = N_NMOS_ROWS + N_PMOS_ROWS, len(COLUMNS)
L_SW = 0.6                 # switch gate length
TG_CELL = (3.0, 7.5)       # cell drain-sense TG, N / P width
TG_ROW = (6.0, 15.0)       # row gate TG
PARK_ROW = 6.0             # row parking device (plan: 3.0; antenna margin, see the docstring)
TG_SENSE = (6.0, 15.0)     # column sense TG
TG_PARK = (3.0, 7.5)       # column parking TG
FINGER = 25.2              # force TG finger width
FORCE_N, FORCE_P = 4, 10   # force TG fingers: N 100.8 um, P 252 um


def lam(v_um: float) -> int:
    n = round(v_um / LAMBDA_UM)
    if abs(n * LAMBDA_UM - v_um) > 1e-6:
        raise ValueError(f"{v_um} um is not on the {LAMBDA_UM} um lambda grid")
    return n


def via_len(h: float) -> float:
    """Smallest length >= h (half lambda steps) of a via1/via2 column whose cut array leaves at
    least 0.7 um of pad at both ends: the kit GDS style puts 0.6 um cut borders ("squares 60 80 80")
    and then pulls every via pad edge that does not meet plain metal in by 0.05 um, so a column
    whose cuts fill it exactly would end with 0.55 um of enclosure (rules 9.VIA1.E1/E3: 0.6 um)."""
    while True:
        um_ = h * LAMBDA_UM
        n = int((um_ - 1.2 + 0.8 + 1e-9) // 1.6)
        if n >= 1 and (um_ - (1.6 * n - 0.8)) / 2 >= 0.7 - 1e-9:
            return h
        h += 0.5


# ---- drawing ---------------------------------------------------------------------------------------
@dataclass
class Layout:
    name: str
    rects: list = field(default_factory=list)
    ports: list = field(default_factory=list)       # (name, layer, x0, y0, x1, y1)

    def paint(self, layer, x0, y0, x1, y1):
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"empty {layer} rectangle {x0},{y0},{x1},{y1}")
        self.rects.append((layer, x0, y0, x1, y1))

    def port(self, name, layer, x0, y0, x1, y1):
        self.ports.append((name, layer, x0, y0, x1, y1))

    def bbox(self):
        xs = [v for r in self.rects for v in (r[1], r[3])]
        ys = [v for r in self.rects for v in (r[2], r[4])]
        return min(xs), min(ys), max(xs), max(ys)

    ORDER = ["nwell", "ndiffusion", "pdiffusion", "polysilicon", "ndcontact", "pdcontact",
             "psubstratepcontact", "nsubstratencontact", "polycontact", "metal1", "metal2",
             "m2contact", "metal3", "m3contact"]

    def magic_tcl(self) -> str:
        out = [f"load {self.name}", "snap internal"]
        for lyr, *_ in self.rects:
            if lyr not in self.ORDER:
                raise ValueError(f"unknown layer {lyr}")
        for layer in self.ORDER:     # contacts after plain layers, so a contact is never overwritten
            for lyr, x0, y0, x1, y1 in self.rects:
                if lyr == layer:
                    out += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"paint {layer}"]
        for name, layer, x0, y0, x1, y1 in self.ports:
            out += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"label {name} c {layer}"]
        bx0, by0, bx1, by1 = self.bbox()
        out += [f"box {um(bx0 - 1)} {um(by0 - 1)} {um(bx1 + 1)} {um(by1 + 1)}", "port makeall",
                f"save {self.name}"]
        return "\n".join(out) + "\n"


@dataclass
class Mos:
    left: tuple      # left S/D tile (x0, y0, x1, y1)
    right: tuple     # right S/D tile
    gate: tuple      # gate poly over the active


def mos_v(lay: Layout, kind: str, x: float, y: float, w: int, l: int) -> Mos:
    """One finger, vertical gate: active [x, x + 16 + l] x [y, y + w] = tile, gap, gate, gap, tile."""
    diff, tile = ("ndiffusion", "ndcontact") if kind == "n" else ("pdiffusion", "pdcontact")
    xa = x + 2 * CT + 2 * GAP + l
    lay.paint(diff, x, y, xa, y + w)
    lay.paint(tile, x, y, x + CT, y + w)
    lay.paint(tile, xa - CT, y, xa, y + w)
    gx = x + CT + GAP
    lay.paint("polysilicon", gx, y - CAP, gx + l, y + w + CAP)
    return Mos((x, y, x + CT, y + w), (xa - CT, y, xa, y + w), (gx, y, gx + l, y + w))


def gate_down(lay: Layout, m: Mos, y_line: float):
    """Gate poly down to a 6 x 6 poly contact centred under the gate on the metal1 line at
    y_line .. y_line + 4."""
    gx0, gy0, gx1, _ = m.gate
    cx = (gx0 + gx1) / 2
    lay.paint("polysilicon", gx0, y_line - 1, gx1, gy0)
    lay.paint("polycontact", cx - CT / 2, y_line - 1, cx + CT / 2, y_line + 5)


def tg(lay: Layout, x: float, a: float, wn: int, wp: int, well_bot: float):
    """Transmission gate: NMOS [B | g | A] at x, PMOS [A | g | B] at x + 30 in a VDD well.
    A: metal1 bridge with a via1 tile at [x + 21, x + 28] x [a, a + 7].
    B: metal1 strap over the top, y [top, top + 4], top = a + max(wn, wp) + 3.
    Returns (mn, mp, top)."""
    mn = mos_v(lay, "n", x, a, wn, 2)
    tp = x + 30
    mp = mos_v(lay, "p", tp, a, wp, 2)
    lay.paint("nwell", tp - 6, well_bot, tp + 24, a + wp + 6)
    lay.paint("metal1", x + 12, a, tp + CT, a + 7)
    lay.paint("m2contact", x + 21, a, x + 28, a + 7)
    top = a + max(wn, wp) + 3
    lay.paint("metal1", x, a + wn, x + CT, top + 4)
    lay.paint("metal1", x, top, tp + 18, top + 4)
    lay.paint("metal1", tp + 12, a + wp, tp + 18, top + 4)
    return mn, mp, top


# ---- floorplan ---------------------------------------------------------------------------------------
# Row lines (metal1, full row width), lambda from the row bottom:
Y_VSS = 0                # p+ substrate tap strip, 6 lambda (VSS)
Y_SEL = 10               # row_sel<r>
Y_SELB = 18              # row_selb<r>
Y_VDD = 26               # VDD (n+ taps of the TG wells)
Y_G = 34                 # G<r> (DUT gates)
Y_ANW = 42               # ANW (PMOS rows: n+ taps of the DUT wells)
A_N, A_P = 42, 52        # device active bottom, NMOS / PMOS rows
COL_MIN = 112            # column pitch at least 112 lambda (force TG of 84 lambda fingers)


def col_geom(c):
    g = COLUMNS[c]
    return None if g is None else (lam(g[0]), lam(g[1]))


def row_pmos(r):
    return r >= N_NMOS_ROWS


def row_height(pmos: bool) -> int:
    wmax = max(g[0] for g in map(col_geom, range(NCOLS)) if g)
    return (A_P if pmos else A_N) + wmax + 3 + VIA + 3


def row_y(r):
    return sum(row_height(row_pmos(k)) for k in range(r))


@dataclass
class ColX:
    x0: int        # column left edge
    width: int
    l: int         # gate length of the column (2 for the open column)
    c: int         # column index (col_sel<c>)

    @property
    def da(self):            # DUT active left = S tile
        return self.x0 + 10

    @property
    def d_tile(self):        # D tile left
        return self.da + CT + GAP + self.l + GAP

    @property
    def tn(self):            # cell TG NMOS active left
        return self.da + 28 + self.l

    @property
    def dc(self):            # D<c> (metal2, 20 lambda)
        return (self.d_tile, self.d_tile + 20)

    @property
    def dsc(self):           # DS<c> (metal2) over the TG bridge via
        m = self.tn + 24.5
        return (m - MW / 2, m + MW / 2)

    @property
    def x1(self):
        return self.x0 + self.width


def columns():
    """Columns in physical order, left to right."""
    out, x = [], 0
    for c in PHYS:
        g = col_geom(c)
        l = g[1] if g else 2
        w = max(COL_MIN, 102 + l)
        out.append(ColX(x, w, l, c))
        x += w
    return out


# ---- array cells ---------------------------------------------------------------------------------------
def draw_cell(lay: Layout, cx: ColX, c: int, y0: float, pmos: bool):
    g = col_geom(c)
    a = y0 + (A_P if pmos else A_N)
    if g is not None:
        w, l = g
        m = mos_v(lay, "p" if pmos else "n", cx.da, a, w, l)
        gate_down(lay, m, y0 + Y_G)
        if pmos:    # DUT well (ANW), n+ taps on the ANW line either side of the gate
            xa1 = m.right[2]
            lay.paint("nwell", cx.da - 6, y0 + Y_ANW - 3, xa1 + 6, a + w + 6)
            lay.paint("nsubstratencontact", cx.da, y0 + Y_ANW, cx.da + CT, y0 + Y_ANW + CT)
            lay.paint("nsubstratencontact", xa1 - CT, y0 + Y_ANW, xa1, y0 + Y_ANW + CT)
        # source: metal1 out to the left, via1 column, metal2, via2 column over the S tile -> plate
        # (plain metal between the via columns is 4.5 lambda wide, so the pads' 0.05 um pull-in
        # in the GDS leaves no narrow metal)
        hs = via_len(max(w, 45))
        sx0, _, sx1, _ = m.left
        lay.paint("metal1", sx0 - 12, a, sx1, a + hs)
        lay.paint("m2contact", sx0 - 12, a, sx0 - 5, a + hs)
        lay.paint("metal2", sx0 - 12, a, sx1 + 0.5, a + hs)
        lay.paint("m3contact", sx0 - 0.5, a, sx1 + 0.5, a + hs)
        dx0, _, dx1, dy1 = m.right
        lay.paint("metal1", dx0, dy1, dx1, dy1 + 3)     # plain metal1 under the via (kit GDS style)
        dy1 += 3
    else:
        # open column: a metal1 pad where the D tile would be, with the same force via and sense route
        dx0, dx1, dy1 = cx.d_tile, cx.d_tile + CT, a + 10
        lay.paint("metal1", dx0, a, dx1, dy1)
    lay.paint("m2contact", dx0, dy1, dx0 + VIA, dy1 + VIA)       # force: top end -> D<c>
    top_via = dy1 + VIA
    lay.paint("metal1", dx0, a, cx.tn + CT, a + 4)               # sense: bottom end -> TG B
    mn, mp, _ = tg(lay, cx.tn, a, lam(TG_CELL[0]), lam(TG_CELL[1]), y0 + Y_VDD - 4)
    gate_down(lay, mn, y0 + Y_SEL)
    gate_down(lay, mp, y0 + Y_SELB)
    tp = cx.tn + 30
    lay.paint("nsubstratencontact", tp + 15, y0 + Y_VDD - 1, tp + 21, y0 + Y_VDD + 5)
    return top_via


# ---- row drivers --------------------------------------------------------------------------------------
@dataclass
class Drv:
    x0: int
    @property
    def pk(self):            # parking device active left
        return self.x0 + 10
    @property
    def tn(self):            # gate TG NMOS active left
        return self.pk + 30
    @property
    def ag(self):            # AG bus (metal2) over the TG bridge via
        m = self.tn + 24.5
        return (m - MW / 2, m + MW / 2)
    @property
    def x1(self):            # right edge of the driver (TG well right edge + 14)
        return self.tn + 30 + 24 + WELL_S


def draw_driver(lay: Layout, d: Drv, r: int, y0: float):
    pmos = row_pmos(r)
    a = y0 + (A_P if pmos else A_N)
    # gate TG: B = G<r> (strap; NMOS B tile drops onto the G line), A -> AG bus
    mn, mp, _ = tg(lay, d.tn, a, lam(TG_ROW[0]), lam(TG_ROW[1]), y0 + Y_VDD - 4)
    gate_down(lay, mn, y0 + Y_SEL)
    gate_down(lay, mp, y0 + Y_SELB)
    lay.paint("nsubstratencontact", d.tn + 45, y0 + Y_VDD - 1, d.tn + 51, y0 + Y_VDD + 5)
    lay.paint("metal1", d.tn, y0 + Y_G, d.tn + CT, a)
    wk = lam(PARK_ROW)
    if not pmos:
        # parking NMOS [VSS | g | G]; gate row_selb; VSS through a metal2 hop onto the VSS strip
        m = mos_v(lay, "n", d.pk, a, wk, 2)
        gate_down(lay, m, y0 + Y_SELB)
        lay.paint("metal1", d.pk + 12, y0 + Y_G, d.pk + 18, a)
        lay.paint("metal1", d.pk - 1, a + wk, d.pk + CT, a + wk + 10)
        lay.paint("m2contact", d.pk - 1, a + wk + 3, d.pk + CT, a + wk + 10)
        lay.paint("metal2", d.pk - 1, y0 + Y_VSS - 0.5, d.pk + CT, a + wk + 10)
        lay.paint("metal1", d.pk - 1, y0 + Y_VSS - 0.5, d.pk + CT, y0 + Y_VSS + 6.5)
        lay.paint("m2contact", d.pk - 1, y0 + Y_VSS - 0.5, d.pk + CT, y0 + Y_VSS + 6.5)
    else:
        # parking PMOS [ANW | g | G] in its own VDD well; gate row_sel
        m = mos_v(lay, "p", d.pk, a, wk, 2)
        gate_down(lay, m, y0 + Y_SEL)
        lay.paint("nwell", d.pk - 6, y0 + Y_VDD - 4, d.pk + 24, a + wk + 6)
        lay.paint("nsubstratencontact", d.pk + 12, y0 + Y_VDD - 1, d.pk + 18, y0 + Y_VDD + 5)
        lay.paint("metal1", d.pk + 12, y0 + Y_G, d.pk + 18, a)
        lay.paint("metal1", d.pk, y0 + Y_ANW, d.pk + CT, a)


# ---- column switches -----------------------------------------------------------------------------------
# Band below row 0 (lambda from the band bottom; the band top is row 0's bottom, array y = 0):
#   VSS p+ strip | ADF bus (metal3) | force NMOS (4 horizontal fingers) | force PMOS (10 fingers) in a
#   VDD well strip with an n+ strip on top | VDD line | park TG | sense TG (its strap is the ADS line)
YB_VSS = 0
YB_ADF, ADF_W = 8, 30
YB_FN = 46


def finger_tiles(y0, n):
    """y ranges of the n + 1 tiles and n gates of a horizontal-finger device starting at y0."""
    tiles, gates, y = [], [], y0
    for k in range(n + 1):
        tiles.append((y, y + CT))
        y += CT
        if k < n:
            gates.append((y + GAP, y + GAP + 2))
            y += 2 * GAP + 2
    return tiles, gates, y


@dataclass
class BandY:
    fn0: float           # force NMOS active bottom / top
    fn1: float
    well0: float         # force PMOS well strip
    fp0: float
    fp1: float
    vdd: float           # n+ strip (VDD) at the top of the force well
    well1: float
    pvdd: float          # VDD line of the park / sense TG wells
    park: float          # park TG active bottom
    pstrap: float        # park TG strap (B -> D<c>)
    sense: float         # sense TG active bottom
    ads: float           # sense TG strap = ADS line
    top: float           # band height


def band_layout() -> BandY:
    fn0 = YB_FN
    fn1 = finger_tiles(fn0, FORCE_N)[2]
    well0 = fn1 + 6
    fp0 = well0 + 6
    fp1 = finger_tiles(fp0, FORCE_P)[2]
    vdd = fp1 + 4
    well1 = vdd + CT + 3
    pvdd = well1 + WELL_S + 4             # small TG wells start 4 below their VDD line
    park = pvdd + 30                      # VDD line, N gate contact (+9), P gate contact (+20), TG
    pstrap = park + max(lam(TG_PARK[0]), lam(TG_PARK[1])) + 3
    sense = pstrap + 29                   # N gate contact (-20), P gate contact (-10), then the TG
    ads = sense + max(lam(TG_SENSE[0]), lam(TG_SENSE[1])) + 3
    top = ads + LW + 3
    return BandY(fn0, fn1, well0, fp0, fp1, vdd, well1, pvdd, park, pstrap, sense, ads, top)


@dataclass
class SwX:
    """x positions of one column switch (lambda)."""
    cx: ColX

    @property
    def fx(self):            # force fingers' active left
        return max(self.cx.x0 + 8, self.cx.dc[0] - 20)

    @property
    def ax(self):            # ADF collector (metal2) over the X tiles
        return (self.cx.tn + 6, self.cx.tn + 26)

    @property
    def sel(self):           # col_sel<c> (metal2)
        return (self.cx.tn + 32, self.cx.tn + 36)

    @property
    def selb(self):          # col_selb<c> (6 lambda from col_sel: a 7 lambda via pad keeps 4 to it)
        return (self.cx.tn + 42, self.cx.tn + 46)


def via12_pad(lay: Layout, line, y):
    """Via1 tile on a vertical metal2 line (x0, x1) at y .. y + 7, with its metal1."""
    m = (line[0] + line[1]) / 2
    lay.paint("m2contact", m - 3.5, y, m + 3.5, y + 7)
    lay.paint("metal1", m - 3.5, y, m + 3.5, y + 7)


def small_gate(lay: Layout, m: Mos, ybot, line):
    """Gate poly down to a contact at ybot .. ybot + 6, metal1 over to a via1 on the select line."""
    gx0, gy0, gx1, _ = m.gate
    cxg = (gx0 + gx1) / 2
    lay.paint("polysilicon", gx0, ybot, gx1, gy0)
    lay.paint("polycontact", cxg - 3, ybot, cxg + 3, ybot + CT)
    m2 = (line[0] + line[1]) / 2
    lay.paint("metal1", min(cxg - 3, m2 - 3.5), ybot, max(cxg + 3, m2 + 3.5), ybot + CT)
    lay.paint("m2contact", m2 - 3.5, ybot - 0.5, m2 + 3.5, ybot + 6.5)
    lay.paint("metal1", m2 - 3.5, ybot - 0.5, m2 + 3.5, ybot + 6.5)


def draw_column_switch(lay: Layout, cx: ColX, B: BandY, yb0: float):
    Y = lambda v: yb0 + v
    sw = SwX(cx)
    d0, d1 = cx.dc
    fw = lam(FINGER)
    fx = sw.fx
    for kind, y0f, n, line in (("n", B.fn0, FORCE_N, sw.sel), ("p", B.fp0, FORCE_P, sw.selb)):
        diff, tile = ("ndiffusion", "ndcontact") if kind == "n" else ("pdiffusion", "pdcontact")
        tiles, gates, yend = finger_tiles(Y(y0f), n)
        lay.paint(diff, fx, Y(y0f), fx + fw, yend)
        for k, (t0, t1) in enumerate(tiles):
            # odd tiles -> D<c>, even tiles -> ADF collector; no contacts under their via
            v = (d0 + 6.5, d0 + 13.5) if k % 2 else (sw.ax[0] + 6.5, sw.ax[0] + 13.5)
            lay.paint("metal1", fx, t0, fx + fw, t1)
            lay.paint(tile, fx, t0, v[0] - 4, t1)
            lay.paint(tile, v[1] + 4, t0, fx + fw, t1)
            lay.paint("m2contact", v[0], t0 - 0.5, v[1], t1 + 0.5)
            lay.paint("metal1", v[0], t0 - 0.5, v[1], t1 + 0.5)
        for g0, g1 in gates:
            lay.paint("polysilicon", fx - CAP, g0, fx + fw + 6, g1)
        py = tiles[0][0] - (12 if kind == "n" else 9)
        lay.paint("polysilicon", fx + fw + 2, py, fx + fw + 6, gates[-1][1])
        lay.paint("polycontact", fx + fw + 1, py, fx + fw + 7, py + CT)
        m2 = (line[0] + line[1]) / 2
        if kind == "n":
            lay.paint("metal1", m2 - 3.5, py, fx + fw + 7, py + CT)
            via12_pad(lay, line, py - 0.5)
        else:
            sx = fx + fw + 10                       # metal1 strap down, right of the fingers
            lay.paint("metal1", fx + fw + 1, py, sx + CT, py + CT)
            lay.paint("metal1", sx, Y(14), sx + CT, py + CT)
            lay.paint("metal1", m2 - 3.5, Y(14), sx + CT, Y(20))
            via12_pad(lay, line, Y(13.5))
    # ADF collector over the X tiles, down to the ADF bus
    lay.paint("metal2", sw.ax[0], Y(YB_ADF), sw.ax[1], Y(B.fp1))
    lay.paint("m3contact", sw.ax[0], Y(YB_ADF), sw.ax[1], Y(YB_ADF + ADF_W))
    # select lines from the band bottom (ports) up to the sense TG gates
    for line in (sw.sel, sw.selb):
        lay.paint("metal2", line[0], Y(0), line[1], Y(B.sense - 2))
    # park TG: D<c> <-> SRC; N gate col_selb, P gate col_sel; well joined with the sense TG well
    mn, mp, ptop = tg(lay, cx.tn, Y(B.park), lam(TG_PARK[0]), lam(TG_PARK[1]), Y(B.pvdd) - 4)
    lay.paint("nsubstratencontact", cx.tn + 45, Y(B.pvdd) - 1, cx.tn + 51, Y(B.pvdd) + 5)
    small_gate(lay, mn, Y(B.pvdd) + 9, sw.selb)
    small_gate(lay, mp, Y(B.pvdd) + 20, sw.sel)
    lay.paint("metal1", d0 + 6.5, ptop, cx.tn + CT, ptop + 4)          # strap left under D<c>
    lay.paint("m2contact", d0 + 6.5, ptop - 1.5, d0 + 13.5, ptop + 5.5)
    lay.paint("metal1", d0 + 6.5, ptop - 1.5, d0 + 13.5, ptop + 5.5)
    lay.paint("metal2", cx.tn + 22.5, Y(B.park), cx.tn + 26.5, Y(B.park) + 18)   # bridge -> plate
    lay.paint("m3contact", cx.tn + 21, Y(B.park) + 11, cx.tn + 28, Y(B.park) + 18)
    # sense TG: DS<c> <-> ADS; N gate col_sel, P gate col_selb
    sn, sp, stop = tg(lay, cx.tn, Y(B.sense), lam(TG_SENSE[0]), lam(TG_SENSE[1]), Y(B.pvdd) - 4)
    small_gate(lay, sn, Y(B.sense) - 20, sw.sel)
    small_gate(lay, sp, Y(B.sense) - 10, sw.selb)
    return sw


# ---- whole block ---------------------------------------------------------------------------------------
X_VSS = (-40, -34)       # VSS metal1 strap
X_VDD = (-28, -21)       # VDD metal2 strap (via1 pads on the VDD lines)
X_ANW = (-15, -8)        # ANW metal2 strap (via1 pads on the ANW lines)


def line_pad(lay: Layout, strap, yline):
    """Metal1 pad and via1 where a 4 lambda metal1 line at yline meets a vertical metal2 strap."""
    lay.paint("metal1", strap[0], yline - 1.5, strap[1], yline + 5.5)
    lay.paint("m2contact", strap[0], yline - 1.5, strap[1], yline + 5.5)


def main_layout():
    lay = Layout(NAME)
    cols = columns()
    xe = cols[-1].x1
    drv = Drv(xe)
    B = band_layout()
    yb0 = -B.top
    ytop = row_y(NROWS)
    ports = {}
    dc_top = {}
    # rows
    for r in range(NROWS):
        y0 = row_y(r)
        pmos = row_pmos(r)
        # VSS strip: p+ taps, plain metal1 where the parking NMOS hop lands (via1 cannot sit on a contact)
        if pmos:
            lay.paint("psubstratepcontact", X_VSS[0], y0, drv.x1, y0 + CT)
        else:
            lay.paint("psubstratepcontact", X_VSS[0], y0, drv.pk - 4, y0 + CT)
            lay.paint("metal1", drv.pk - 4, y0 - 0.5, drv.pk + 9, y0 + CT + 0.5)
            lay.paint("psubstratepcontact", drv.pk + 9, y0, drv.x1, y0 + CT)
        for y in (Y_SEL, Y_SELB, Y_G):
            lay.paint("metal1", 0, y0 + y, drv.x1, y0 + y + LW)
        lay.paint("metal1", X_VDD[0], y0 + Y_VDD, drv.tn + 51, y0 + Y_VDD + LW)
        line_pad(lay, X_VDD, y0 + Y_VDD)
        if pmos:
            lay.paint("metal1", X_ANW[0], y0 + Y_ANW, drv.pk + CT, y0 + Y_ANW + LW)
            line_pad(lay, X_ANW, y0 + Y_ANW)
        for cx in cols:
            dc_top[cx.c] = draw_cell(lay, cx, cx.c, y0, pmos)
        draw_driver(lay, drv, r, y0)
        ports[f"row_sel{r}"] = ("metal1", drv.x1 - 4, y0 + Y_SEL, drv.x1, y0 + Y_SEL + LW)
        ports[f"row_selb{r}"] = ("metal1", drv.x1 - 4, y0 + Y_SELB, drv.x1, y0 + Y_SELB + LW)
    # band: strips and lines across all columns
    Y = lambda v: yb0 + v
    lay.paint("psubstratepcontact", X_VSS[0], Y(YB_VSS), xe, Y(YB_VSS) + CT)
    lay.paint("metal3", X_VSS[0], Y(YB_ADF), xe, Y(YB_ADF + ADF_W))
    fx0 = SwX(cols[0]).fx
    lay.paint("nwell", fx0 - 6, Y(B.well0), SwX(cols[-1]).fx + lam(FINGER) + 6, Y(B.well1))
    lay.paint("nsubstratencontact", fx0 - 3, Y(B.vdd), SwX(cols[-1]).fx + lam(FINGER) + 3, Y(B.vdd) + CT)
    lay.paint("metal1", X_VDD[0], Y(B.vdd) + 1, fx0 - 3, Y(B.vdd) + 5)
    line_pad(lay, X_VDD, Y(B.vdd) + 1)
    lay.paint("metal1", X_VDD[0], Y(B.pvdd), xe, Y(B.pvdd) + LW)
    line_pad(lay, X_VDD, Y(B.pvdd))
    lay.paint("metal1", X_VSS[1] + 3, Y(B.ads), xe, Y(B.ads) + LW)      # ADS line
    # ADS exit to metal3 (the VSS metal1 strap is in the way of metal1): via1 below the line end,
    # narrow metal2, via2 lower still (no via2 on via1), metal3 pad left of the source plate
    ya = Y(B.ads)
    lay.paint("metal1", -17, ya - 3, -10, ya + LW)
    lay.paint("m2contact", -17, ya - 3, -10, ya + LW)
    lay.paint("metal2", -15.5, ya - 7, -11.5, ya - 3)
    lay.paint("m3contact", -17, ya - 14, -10, ya - 7)
    for cx in cols:
        c = cx.c
        lay.paint("metal2", cx.dc[0], Y(B.fn0), cx.dc[1], dc_top[c])      # ends at the top via
        lay.paint("metal2", cx.dsc[0], Y(B.sense), cx.dsc[1], ytop)
        sw = draw_column_switch(lay, cx, B, yb0)
        ports[f"col_sel{c}"] = ("metal2", sw.sel[0], Y(0), sw.sel[1], Y(0) + 4)
        ports[f"col_selb{c}"] = ("metal2", sw.selb[0], Y(0), sw.selb[1], Y(0) + 4)
    # straps, AG bus, source plate
    lay.paint("metal1", X_VSS[0], Y(0), X_VSS[1], ytop)
    lay.paint("metal2", X_VDD[0], Y(0), X_VDD[1], ytop)
    lay.paint("metal2", X_ANW[0], row_y(N_NMOS_ROWS), X_ANW[1], ytop)
    lay.paint("metal2", drv.ag[0], 0, drv.ag[1], ytop)
    # source plate (metal3); ASS: a metal3 line in a slot from the left edge to the plate centre,
    # between the source vias of rows 5 and 6
    ys = ass_y()
    xc = ass_x(cols)
    lay.paint("metal3", 0, Y(B.park), xe, ys - 4)
    lay.paint("metal3", 0, ys + MW + 4, xe, ytop)
    lay.paint("metal3", xc, ys - 4, xe, ys + MW + 4)
    lay.paint("metal3", X_VSS[1] + 3, ys, xc, ys + MW)
    ports.update({
        "VSS": ("metal1", X_VSS[0], Y(0), X_VSS[1], Y(0) + 4),
        "VDD": ("metal2", X_VDD[0], Y(0), X_VDD[1], Y(0) + 4),
        "ANW": ("metal2", X_ANW[0], ytop - 4, X_ANW[1], ytop),
        "AG": ("metal2", drv.ag[0], ytop - 4, drv.ag[1], ytop),
        "ADF": ("metal3", X_VSS[0], Y(YB_ADF), X_VSS[0] + 4, Y(YB_ADF + ADF_W)),
        "ADS": ("metal1", X_VSS[1] + 3, Y(B.ads), X_VSS[1] + 7, Y(B.ads) + LW),
        "SRC": ("metal3", 0, ytop - 4, 4, ytop),
    })
    for name, (layer, *box) in ports.items():
        lay.port(name, layer, *box)
    # connection points for the chip routing (not ports: ASS is the source plate's sense stub)
    pins = dict(ports)
    pins["ASS"] = ("metal3", X_VSS[1] + 3, ys, X_VSS[1] + 7, ys + MW)
    pins["SRC_EDGE"] = ("metal3", 0, Y(B.park), 4, ytop)               # plate left edge (ASF)
    pins["ADS_M3"] = ("metal3", -17, Y(B.ads) - 14, -10, Y(B.ads) - 7)    # ADS landing on metal3
    pins["ANW_BOT"] = ("metal2", X_ANW[0], row_y(N_NMOS_ROWS), X_ANW[1], row_y(N_NMOS_ROWS) + 4)
    for r in range(NROWS):
        y0 = row_y(r)
        pins[f"row_line{r}"] = ("metal1", drv.x1 - 4, y0 + Y_SEL, drv.x1, y0 + Y_SELB + LW)
    return lay, dict(band=B, cols=cols, drv=drv, ytop=ytop, yb0=yb0, pins=pins)


def ass_y():
    """y of the ASS line: between the source via columns of rows 5 and 6 (plate centre)."""
    r = NROWS // 2
    lo = row_y(r - 1) + (A_P if row_pmos(r - 1) else A_N) + via_len(max(g[0] for g in map(col_geom, range(NCOLS)) if g))
    hi = row_y(r) + (A_P if row_pmos(r) else A_N)
    y = (lo + hi) / 2 - MW / 2
    if y - 4 < lo + 1 or y + MW + 4 > hi - 1:
        raise ValueError("no room for the ASS slot between rows")
    return round(y)


def ass_x(cols):
    """x where the ASS line meets the plate: middle of the DUT columns."""
    return round((cols[0].x0 + cols[-1].x1) / 2)


# ---- schematic netlist (from the circuit description above, not from the drawing) ------------------
def netlist() -> str:
    pins = (["AG", "ADF", "ADS", "SRC", "ANW", "VDD", "VSS"]
            + [f"col_sel{c}" for c in range(NCOLS)] + [f"col_selb{c}" for c in range(NCOLS)]
            + [f"row_sel{r}" for r in range(NROWS)] + [f"row_selb{r}" for r in range(NROWS)])
    L = f"L={L_SW:g}u"
    out = [f"* {NAME}: Kelvin array {NROWS} rows x {NCOLS} columns (see etri050_array.py)",
           f".subckt {NAME} " + " ".join(pins)]
    k = 0

    def m(d, g, s, b, model, w, l=L):
        nonlocal k
        k += 1
        out.append(f"M{k} {d} {g} {s} {b} {model} W={w:g}u {l}")

    for r in range(NROWS):
        pm = row_pmos(r)
        for c in range(NCOLS):
            if COLUMNS[c] is not None:
                w, l = COLUMNS[c]
                m(f"D{c}", f"G{r}", "SRC", "ANW" if pm else "VSS", "pfet" if pm else "nfet", w, f"L={l:g}u")
            m(f"D{c}", f"row_sel{r}", f"DS{c}", "VSS", "nfet", TG_CELL[0])
            m(f"D{c}", f"row_selb{r}", f"DS{c}", "VDD", "pfet", TG_CELL[1])
        m("AG", f"row_sel{r}", f"G{r}", "VSS", "nfet", TG_ROW[0])
        m("AG", f"row_selb{r}", f"G{r}", "VDD", "pfet", TG_ROW[1])
        if pm:
            m("ANW", f"row_sel{r}", f"G{r}", "VDD", "pfet", PARK_ROW)
        else:
            m("VSS", f"row_selb{r}", f"G{r}", "VSS", "nfet", PARK_ROW)
    for c in range(NCOLS):
        for _ in range(FORCE_N):
            m("ADF", f"col_sel{c}", f"D{c}", "VSS", "nfet", FINGER)
        for _ in range(FORCE_P):
            m("ADF", f"col_selb{c}", f"D{c}", "VDD", "pfet", FINGER)
        m("ADS", f"col_sel{c}", f"DS{c}", "VSS", "nfet", TG_SENSE[0])
        m("ADS", f"col_selb{c}", f"DS{c}", "VDD", "pfet", TG_SENSE[1])
        m(f"D{c}", f"col_selb{c}", "SRC", "VSS", "nfet", TG_PARK[0])
        m(f"D{c}", f"col_sel{c}", "SRC", "VDD", "pfet", TG_PARK[1])
    out.append(".ends")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    lay, info = main_layout()
    for ext in (".mag", ".ext", ".spice", ".gds"):
        (args.out / f"{lay.name}{ext}").unlink(missing_ok=True)
    run_magic(lay.magic_tcl() + f"cif ostyle lambda=0.30(ETRI)\ngds write {lay.name}.gds\n",
              args.out, f"{lay.name}_build.log")
    if not (args.out / f"{lay.name}.gds").exists():
        sys.exit(f"Magic did not write {lay.name}.gds (see {args.out / (lay.name + '_build.log')})")
    pins = {k: {"layer": v[0], "box": [round(t * LAMBDA_UM, 3) for t in v[1:]]} for k, v in info["pins"].items()}
    (args.out / f"{lay.name}_pins.json").write_text(json.dumps({
        "cell": lay.name, "unit": "um, block coordinates (origin: row 0 bottom, column at the left edge)",
        "columns_left_to_right": [cx.c for cx in info["cols"]], "pins": pins}, indent=1))
    (args.out / "sch").mkdir(exist_ok=True)
    (args.out / "sch" / f"{lay.name}.spice").write_text(netlist())
    x0, y0, x1, y1 = lay.bbox()
    print(f"{lay.name}: {(x1 - x0) * LAMBDA_UM:.1f} x {(y1 - y0) * LAMBDA_UM:.1f} um, "
          f"{len(lay.rects)} rectangles, {len(lay.ports)} ports")
    if args.check:
        ok, line = etri_check(lay.name, str(args.out / "sch" / f"{lay.name}.spice"), args.out)
        print("  " + line)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
