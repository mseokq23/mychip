#!/usr/bin/env python3
"""CBCM block of pdkv (charge-based capacitance measurement, ten structures), generated from code.

Circuit (plan section "CBCM 용량 측정"; designs/etri050/sim/blocks/cbcm.py simulated the principle,
designs/etri050/sim/blocks/cbcm_block.py simulates this netlist):

  clock     cbcm_clk (control block, = CCK while mode 10) -> non-overlap generator as in the plan
            simulation: INVX1 for clkb, p1 = NOR(clk, d2), p2 = NOR(clkb, d1), d1 / d2 = p1 / p2 delayed
            by NDELAY (6) INVX1. PCK = p2 through INVX1 + INVX4, NG = p1 through INVX1 + INVX4 (SPICE and Netgen
            ignore case, so no two node names may differ only in case).
  cell i    (i = 0..9, cbcm_en<i>) PG<i> = NAND2X1(PCK, en<i>): only the selected cell's PMOS clock runs.
            Pseudo-inverter pair: DUT PMOS 6/0.6 from VCD (its N-well on VCD) and NMOS 3/0.6 to VSS on
            node ND<i>; REF the same from VCR on node NR<i>; PMOS gates PG<i>, NMOS gates NG (global:
            in an unselected cell the NMOS keeps both nodes at VSS and the PMOS stays off).
            C = (I(VCD) - I(VCR)) / (V f), V = VCD = VCR.
  structure on ND<i>; NR<i> ends in a stub of the same metal (plan: "빈 셀(오프셋 교정)" ...):
      0 empty      no structure: DUT/REF offset of the pair and its stubs
      1 PIP        poly2 30 x 30 um over poly1 (PDK pipcap layer set), poly1 to VSS
      2 MET1-field metal1 plate over field oxide
      3 MET2-MET1  metal2 plate over a metal1 plate at VSS
      4 MET3-MET2  metal3 plate over a metal2 plate at VSS
      5 MET1 comb  interdigitated metal1, the other comb at VSS
      6 N+ area    N+ diffusion in the P-well, area dominated
      7 N+ edge    N+ fingers 0.9 um wide, perimeter dominated
      8 gate L10   NMOS W 48 / L 10.5 um, gate on ND, S, D, B at VSS (plan: W 50 / L 10)
      9 gate L2    NMOS W 240 / L 2.1 um as 5 x 48 um fingers: the same gate area, 5x the gate edge

Ports: clk, en0..en9, VCD, VCR, VDD, VSS.

  python3 designs/etri050/gen/etri050_cbcm.py [--out DIR] [--check] [--netlist-only]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etri050_mos import REPO, etri_check, run_magic  # noqa: E402

DEFAULT_OUT = REPO / "designs/etri050/cbcm/build"
NAME = "cbcm"
NCELL = 10

# ---- circuit (um) ------------------------------------------------------------------------------------
PSEUDO_P = (6.0, 0.6)          # pseudo-inverter PMOS W / L (plan: P 6 / N 3)
PSEUDO_N = (3.0, 0.6)
GATE_L10 = (48.0, 10.5, 1)     # structure 8: W, L, fingers. Plan W 50 / L 10 and W 250 / L 2: on the
GATE_L2 = (48.0, 2.1, 5)       # 0.3 um lambda grid the same gate area (504 um2) and 5x the gate edge
                               # need L 10.5 / 2.1; fingers of W 48 (rule 2.ACT.W2: W <= 100 um)
NDELAY = 6                     # inverters in each delay chain of the non-overlap generator. The plan
                               # (one pair driven by INVX4) has 4; here a NAND2X1 drives two PMOS gates
                               # and one INVX4 all twenty NMOS gates, and 4 stages leave 0.12-0.14 ns
                               # between PMOS off and NMOS on (gate at VCD - 0.9 V / 0.7 V; TT, FF 5.5 V,
                               # SS 125 C 4.5 V), 6 stages 0.34-0.46 ns with the same C (cbcm_block.py).
                               # 8 stages lose the clock phases at FF 5.5 V.
STRUCTURES = ["empty", "PIP 30x30", "MET1-field", "MET2-MET1", "MET3-MET2", "MET1 comb",
              "N+ area", "N+ edge", "gate W48/L10.5", "gate 5xW48/L2.1"]
STDCELLS = ("INVX1", "INVX4", "NOR2X1", "NAND2X1")


def kit_stdcells_spice() -> str:
    """The kit's LVS netlist of the standard cells this block uses (nfet / pfet)."""
    import os
    dk = os.environ.get("ETRI050_DK", str(REPO / ".pdk/ETRI050_DesignKit"))
    if not Path(dk).is_dir():
        dk = str(Path.home() / "ETRI050_DesignKit")
    txt = (Path(dk) / "digital_ETRI/khu_etri050_stdcells.spice").read_text()
    out = []
    for cell in STDCELLS:
        m = re.search(r"^\.subckt %s .*?^\.ends.*?$" % cell, txt, re.S | re.M | re.I)
        if not m:
            raise SystemExit(f"{cell} not in the kit standard-cell netlist")
        out.append(m.group(0))
    return "\n".join(out) + "\n"


def netlist(with_cells: bool = True) -> str:
    """Schematic netlist of the block, written from the circuit above (not from the drawing)."""
    pins = ["clk"] + [f"en{i}" for i in range(NCELL)] + ["VCD", "VCR", "VDD", "VSS"]
    out = [f"* {NAME}: CBCM, {NCELL} cells (see etri050_cbcm.py)"]
    if with_cells:
        out.append(kit_stdcells_spice())
    out.append(f".subckt {NAME} " + " ".join(pins))
    s = "VDD VSS"
    out += [f"XCK clk clkb {s} INVX1",
            f"XN1 clk d2 p1 {s} NOR2X1",
            f"XN2 clkb d1 p2 {s} NOR2X1"]
    for tag, src, dst in (("A", "p1", "d1"), ("B", "p2", "d2")):
        prev = src
        for k in range(1, NDELAY + 1):
            nxt = dst if k == NDELAY else f"{tag.lower()}{k}"
            out.append(f"X{tag}{k} {prev} {nxt} {s} INVX1")
            prev = nxt
    out += [f"XP1 p2 p2n {s} INVX1", f"XP2 p2n PCK {s} INVX4",
            f"XQ1 p1 p1n {s} INVX1", f"XQ2 p1n NG {s} INVX4"]
    k = 0

    def m(d, g, src, b, model, w, l):
        nonlocal k
        k += 1
        out.append(f"M{k} {d} {g} {src} {b} {model} W={w:g}u L={l:g}u")

    for i in range(NCELL):
        out.append(f"XG{i} PCK en{i} PG{i} {s} NAND2X1")
        m(f"ND{i}", f"PG{i}", "VCD", "VCD", "pfet", *PSEUDO_P)
        m(f"ND{i}", "NG", "VSS", "VSS", "nfet", *PSEUDO_N)
        m(f"NR{i}", f"PG{i}", "VCR", "VCR", "pfet", *PSEUDO_P)
        m(f"NR{i}", "NG", "VSS", "VSS", "nfet", *PSEUDO_N)
    for cell, (w, l, nf) in ((8, GATE_L10), (9, GATE_L2)):
        for _ in range(nf):
            m("VSS", f"ND{cell}", "VSS", "VSS", "nfet", w, l)
    out.append(".ends")
    return "\n".join(out) + "\n"


# ==== layout =========================================================================================
# Lambda units (0.3 um), half lambda allowed; block origin = lower left (die x 1144.0, y 456.0 in
# chip/assemble.py). Frame, bottom to top:
#   y    0-120   non-overlap generator, one standard-cell row (gnd rail on the die's south VSS line);
#                bottom structures (cells 1, 5-9) to its right and above it, up to y 337
#   y  341-419   lower band: pseudo-inverter pairs of the bottom structures, mirrored (rail side up)
#   y  415-535   lower row: their NAND2X1 gates (normal); tracks for PCK and en over the row
#   y  535-655   upper row: NAND2X1 gates of cells 0, 2-4 (flipped); vdd rail at 535 shared
#   y  651-729   upper band: pseudo-inverter pairs of the top structures (cell 0: no structure)
#   y  739-1079  top structures: the three metal plates
# West strip x 0-122: NG and PCK risers and the en jogs (en pins at the control block's pin heights).
# Every metal2 / metal3 shape added here keeps 3.5 lambda (1.05 um) from other nets (rule document
# 10.MET2.S1, 12.MET3.S1: 1.0 um), checked by spacing_errors() before Magic runs.
from etri050_array import Layout  # noqa: E402

LAMBDA_UM = 0.3
W, H = 986, 1083
ORIGIN_DIE = (1144.0, 456.0)
Y_LROW, Y_MID, Y_UROW = 415, 535, 655
BAND_TOP = 74                     # pair node stubs end this far from the rail edge
Y_TOP0 = 739                      # top structures
Y_BOT1 = 337                      # bottom structures end
SP = 3.5                          # metal2 / metal3 spacing used for the added routing (1.05 um)
EN_Y = [855 - 20 * i for i in range(NCELL)]   # en<i> pin centres (control block cbcm_en<i>)
CLK_Y = 85                                    # cbcm_clk pin centre
X_NG, X_PCK = 131, 16                         # NG riser east of the en jogs, PCK riser west of them
X_JOG = [28 + 10 * k for k in range(NCELL)]   # en jog columns
X_NOVL = 30                                   # generator row start
X_VDD = (650, 670)                            # VDD riser (from S7 PVDD)
X_VCD, X_VCR = (962, 966), (972, 976)         # VCD / VCR risers inside the block's east edge
CELL_W = {"INVX1": 30, "INVX4": 40, "NOR2X1": 40, "NAND2X1": 40}
# metal2 pins of the kit cells (lambda, normal orientation): m2p pin plus the via1 pad next to it
PINS = {"INVX1": {"A": (1.5, 31.5, 8.5, 45.5), "Y": (11.5, 44.5, 18.5, 58.5)},
        "INVX4": {"A": (1.5, 44.5, 8.5, 58.5), "Y": (21.5, 44.5, 28.5, 58.5)},
        "NOR2X1": {"A": (1.5, 41.5, 8.5, 55.5), "B": (21.5, 41.5, 28.5, 55.5), "Y": (11.5, 31.5, 18.5, 45.5)},
        "NAND2X1": {"A": (1.5, 54.5, 8.5, 68.5), "B": (21.5, 54.5, 28.5, 68.5), "Y": (11.5, 51.5, 18.5, 65.5)}}
# stub centre per pin (4 lambda wide stubs, kept 6 lambda from the cell's other pins)
STUB_X = {"INVX1": {"A": 3.5, "Y": 15}, "INVX4": {"A": 5, "Y": 25},
          "NOR2X1": {"A": 5, "B": 25, "Y": 15}, "NAND2X1": {"A": 4.5, "B": 25.5, "Y": 15}}


class Block(Layout):
    """Layout plus standard-cell instances and a net name on every routing rectangle."""

    def __init__(self, name):
        super().__init__(name)
        self.cells = []          # (cell, x, y, flipped, instance)
        self.netrects = []       # (net, layer, x0, y0, x1, y1, kind) for the spacing check
        self.pinrects = []       # kit cell pins (net, layer, x0, y0, x1, y1)

    def r(self, net, layer, x0, y0, x1, y1):
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        self.paint(layer, x0, y0, x1, y1)
        self.netrects.append((net, layer, x0, y0, x1, y1))

    def cell(self, cell, x, y, flipped, inst):
        self.cells.append((cell, x, y, flipped, inst))
        out = {}
        for pin, (a, b, c, d) in PINS[cell].items():
            if flipped:
                b, d = 120 - d, 120 - b
            out[pin] = (x + a, y + b, x + c, y + d)
        return out

    def magic_tcl(self) -> str:
        tcl = super().magic_tcl()
        head, rest = tcl.split("\n", 2)[:2], tcl.split("\n", 2)[2]
        lines = []
        for cell, x, y, flipped, inst in self.cells:
            lines += [f"box {x * LAMBDA_UM:.2f}um {y * LAMBDA_UM:.2f}um {x * LAMBDA_UM:.2f}um {y * LAMBDA_UM:.2f}um",
                      f"getcell {cell}{' v' if flipped else ''}", f"identify {inst}"]
        return "\n".join(head + lines) + "\n" + rest

    def via2(self, net, x, y):
        """via2 tile centred at (x, y)."""
        self.r(net, "m3contact", x - 3.5, y - 3.5, x + 3.5, y + 3.5)

    def via1(self, net, x, y):
        self.r(net, "m2contact", x - 3.5, y - 3.5, x + 3.5, y + 3.5)


# ---- pseudo-inverter pair (upper orientation: rail edge at y 0, devices above) -----------------------
# REF half left, DUT half right. NMOS 3/0.6 at y 8-18 (sources to the rail), PMOS 6/0.6 at y 40-60 in
# their own wells (VCR left, VCD right, 14 lambda apart), drains joined by the node columns NR (x 22-28)
# and ND (x 54-60) that run on to y 74. NG: poly bus y 22-24 -> contact -> via1 -> via2 -> band rail;
# PG: poly bus y 62-64 -> contact -> metal1 down -> via1 at y 10-17 -> metal2 down to the NAND's Y.
RAIL = {"NG": (26, 30), "VCR": (36, 40), "VCD": (46, 50)}   # band rails (metal3), pair coordinates
PAIR_X = (-8, 90)
PG_X = (43.5, 50.5)
NODE_X = {"NR": (22, 28), "ND": (54, 60)}


def pair_shapes(i):
    S = []

    def r(net, l, x0, y0, x1, y1):
        S.append((net, l, x0, y0, x1, y1))

    nd, nr, pg = f"ND{i}", f"NR{i}", f"PG{i}"
    # NMOS
    r(None, "ndiffusion", 10, 8, 28, 18)
    r("VSS", "ndcontact", 10, 8, 16, 18)
    r(nr, "ndcontact", 22, 8, 28, 18)
    r(None, "ndiffusion", 54, 8, 72, 18)
    r(nd, "ndcontact", 54, 8, 60, 18)
    r("VSS", "ndcontact", 66, 8, 72, 18)
    r(None, "polysilicon", 18, 6, 20, 24)
    r(None, "polysilicon", 62, 6, 64, 24)
    r(None, "polysilicon", 18, 22, 64, 24)
    r("NG", "polycontact", 31.5, 20, 37.5, 26)
    r("NG", "metal1", 31, 10, 38, 26)
    r("NG", "m2contact", 31, 10, 38, 17)
    r("NG", "metal2", 31, 10, 38, 31.5)
    r("NG", "m3contact", 31, 24.5, 38, 31.5)
    # PMOS
    r(None, "pdiffusion", 10, 40, 28, 60)
    r("VCR", "pdcontact", 10, 40, 16, 60)
    r(nr, "pdcontact", 22, 40, 28, 60)
    r(None, "pdiffusion", 54, 40, 72, 60)
    r(nd, "pdcontact", 54, 40, 60, 60)
    r("VCD", "pdcontact", 66, 40, 72, 60)
    r(None, "polysilicon", 18, 38, 20, 64)
    r(None, "polysilicon", 62, 38, 64, 64)
    r(None, "polysilicon", 18, 62, 64, 64)
    r(pg, "polycontact", 44, 60, 50, 66)
    r(pg, "metal1", 43.5, 10, 50.5, 66)
    r(pg, "m2contact", 43.5, 10, 50.5, 17)
    r(pg, "metal2", 43.5, -4, 50.5, 17)
    # wells, well taps and supplies
    r(None, "nwell", -6, 34, 34, 66)
    r(None, "nwell", 48, 34, 88, 66)
    r("VCR", "nsubstratencontact", 0, 40, 6, 60)
    r("VCD", "nsubstratencontact", 76, 40, 82, 60)
    r("VCR", "metal1", -8, 40, 16, 60)
    r("VCR", "m2contact", -8, 45.5, -1, 52.5)
    r("VCR", "metal2", -8, 34.5, -1, 52.5)
    r("VCR", "m3contact", -8, 34.5, -1, 41.5)
    r("VCD", "metal1", 66, 40, 90, 62.5)
    r("VCD", "m2contact", 83, 55.5, 90, 62.5)
    r("VCD", "metal2", 83, 44.5, 90, 62.5)
    r("VCD", "m3contact", 83, 44.5, 90, 51.5)
    # VSS: NMOS sources and p+ taps in the rail
    r("VSS", "psubstratepcontact", 10, -3, 16, 3)
    r("VSS", "psubstratepcontact", 66, -3, 72, 3)
    r("VSS", "metal1", 10, -4, 16, 18)
    r("VSS", "metal1", 66, -4, 72, 18)
    # node columns
    r(nr, "metal1", 22, 8, 28, BAND_TOP)
    r(nd, "metal1", 54, 8, 60, BAND_TOP)
    return S


def place_pair(blk, i, x0, upper):
    """Pair of cell i at x0; upper band (above the upper row) or lower band (mirrored)."""
    for net, l, a, b, c, d in pair_shapes(i):
        if upper:
            y0, y1 = Y_UROW + b, Y_UROW + d
        else:
            y0, y1 = Y_LROW - d, Y_LROW - b
        if net is None:
            blk.paint(l, x0 + a, y0, x0 + c, y1)
        else:
            blk.r(net, l, x0 + a, y0, x0 + c, y1)


def band_y(upper, local):
    """Absolute y range of a pair-coordinate y range."""
    a, b = local
    return (Y_UROW + a, Y_UROW + b) if upper else (Y_LROW - b, Y_LROW - a)


def node_end(upper):
    """y where the node columns leave the band (towards the structures)."""
    return Y_UROW + BAND_TOP if upper else Y_LROW - BAND_TOP


# ---- floorplan of the cells --------------------------------------------------------------------------
# cell -> (band, pair x0). Top structures sit over the upper band, bottom structures under the lower one.
PAIRS = {0: ("upper", 860), 2: ("upper", 200), 3: ("upper", 436), 4: ("upper", 680),
         8: ("lower", 145.5), 9: ("lower", 256.5), 6: ("lower", 381.5), 7: ("lower", 492.5),
         5: ("lower", 700), 1: ("lower", 850)}


def draw_pairs_and_gates(blk):
    """Pairs, their NAND2X1 (Y straight under / over the PG lead) and the PG links."""
    nands = {}
    for i, (band, x0) in PAIRS.items():
        upper = band == "upper"
        place_pair(blk, i, x0, upper)
        nx = x0 + PG_X[0] - PINS["NAND2X1"]["Y"][0]          # NAND Y pin under the PG lead
        if upper:
            pins = blk.cell("NAND2X1", nx, Y_MID, True, f"XG{i}")
            blk.r(f"PG{i}", "metal2", x0 + PG_X[0], pins["Y"][3], x0 + PG_X[1], Y_UROW - 4)
        else:
            pins = blk.cell("NAND2X1", nx, Y_LROW, False, f"XG{i}")
            blk.r(f"PG{i}", "metal2", x0 + PG_X[0], Y_LROW + 4, x0 + PG_X[1], pins["Y"][1])
        nands[i] = (upper, nx, pins)
    return nands


# ---- band rails (metal3) ----------------------------------------------------------------------------
def draw_band_rails(blk):
    for upper in (False, True):
        xs = [x0 for i, (band, x0) in PAIRS.items() if (band == "upper") == upper]
        for net, loc in RAIL.items():
            y0, y1 = band_y(upper, loc)
            if net == "NG":
                x_start = X_NG - 3.5
            else:
                x_start = min(xs) + PAIR_X[0]
            # NG runs on past the last pair's ND column (x 54-60) as it does past every other pair's:
            # ending at its via (x 38), it left the east pairs' ND without the 0.18 fF that NG adds to
            # every other ND (cbcm_c.py), and the empty cell 0 is the reference for all of them
            x_end = {"NG": max(xs) + 66, "VCD": X_VCD[1] + 3.5, "VCR": X_VCR[1] + 3.5}[net]
            blk.r(net, "metal3", x_start, y0, x_end, y1)


# ---- generator row ----------------------------------------------------------------------------------
NOVL_CELLS = ([("XQ2", "INVX4"), ("XQ1", "INVX1"), ("XP2", "INVX4"), ("XP1", "INVX1"), ("XCK", "INVX1"),
               ("XN1", "NOR2X1"), ("XN2", "NOR2X1")]
              + [(f"XA{k}", "INVX1") for k in range(1, NDELAY + 1)]
              + [(f"XB{k}", "INVX1") for k in range(1, NDELAY + 1)])
NOVL_TRACKS = [64, 74, 83, 93, 103]      # metal3 tracks over the row (track 2 carries cbcm_clk in);
                                         # track 0's pads start 4 lambda over the highest pin (y 58.5)


def novl_nets():
    """net -> [(instance, pin)] of the generator (outputs NG and PCK also go to the west risers)."""
    nets = {"NG": [("XQ2", "Y")], "PCK": [("XP2", "Y")], "p1n": [("XQ1", "Y"), ("XQ2", "A")],
            "p2n": [("XP1", "Y"), ("XP2", "A")], "p1": [("XN1", "Y"), ("XQ1", "A"), ("XA1", "A")],
            "p2": [("XN2", "Y"), ("XP1", "A"), ("XB1", "A")], "clk": [("XCK", "A"), ("XN1", "A")],
            "clkb": [("XCK", "Y"), ("XN2", "A")],
            "d1": [(f"XA{NDELAY}", "Y"), ("XN2", "B")], "d2": [(f"XB{NDELAY}", "Y"), ("XN1", "B")]}
    for t in "AB":
        for k in range(1, NDELAY):
            nets[f"{t.lower()}{k}"] = [(f"X{t}{k}", "Y"), (f"X{t}{k + 1}", "A")]
    return nets


def draw_novl(blk):
    x = X_NOVL
    where = {}
    for inst, cell in NOVL_CELLS:
        blk.cell(cell, x, 0, False, inst)
        where[inst] = (cell, x)
        x += CELL_W[cell]
    x_end = x
    nets = novl_nets()
    # stub x per (net) and the extra west columns
    points = {}
    for net, pins in nets.items():
        pts = []
        for inst, pin in pins:
            cell, cx = where[inst]
            pts.append((cx + STUB_X[cell][pin], PINS[cell][pin][3]))           # (x centre, pin top)
        points[net] = pts
    extra = {"NG": X_NG, "PCK": X_PCK, "clk": 0}
    spans = {}
    for net, pts in points.items():
        xs = [p[0] for p in pts] + ([extra[net]] if net in extra else [])
        spans[net] = (min(xs) - 3.5, max(xs) + 3.5)
    # left-edge track assignment; cbcm_clk is fixed on track 2 (its pin height)
    track_of = {"clk": 2}
    busy = {t: [] for t in range(len(NOVL_TRACKS))}
    busy[2].append(spans["clk"])
    for net in sorted((n for n in spans if n != "clk"), key=lambda n: spans[n][0]):
        lo, hi = spans[net]
        for t in range(len(NOVL_TRACKS)):
            if all(hi + SP <= a or lo >= b + SP for a, b in busy[t]):
                busy[t].append((lo, hi))
                track_of[net] = t
                break
        else:
            raise SystemExit(f"generator row: no track for {net}")
    for net, pts in points.items():
        ty = NOVL_TRACKS[track_of[net]]
        lo, hi = spans[net]
        blk.r(net, "metal3", 0 if net == "clk" else lo, ty, hi, ty + 4)
        for xc, top in pts:
            blk.r(net, "metal2", xc - 2, top - 1, xc + 2, ty + 2)
            blk.via2(net, xc, ty + 2)
    # rails: gnd (VSS) along the whole bottom edge, vdd over to the VDD riser
    blk.r("VSS", "metal1", X_NOVL - 3, -4, W, 4)
    blk.r("VDD", "metal1", X_NOVL - 3, 116, X_VDD[1], 124)
    return track_of, x_end


# ---- NAND inputs: PCK and en tracks over the rows ------------------------------------------------------
# Track via pads stay 4 lambda (1.2 um) from the pins: the kit's GDS style pulls every via pad edge that
# does not meet plain metal in by 0.05 um, so pad, stub and pin closer than 1.0 um would leave notches.
LOW_TRACKS_A = [489, 498, 507, 516, 525]     # lower row, above its pins (stubs up from y 483.5)
LOW_TRACKS_B = [460, 450, 440, 430]          # lower row, under its pins (stubs down from y 469.5)
UP_TRACKS_A = [577, 568, 559, 550, 541]      # upper row, under its pins (stubs down from y 586.5)
UP_TRACKS_B = [606, 616, 626, 636]           # upper row, above its pins (stubs up from y 600.5)


def draw_row_well(blk, nands):
    """One N-well along the shared vdd rail over the span of the NAND2X1 cells: the wells of a normal
    lower-row cell (y 482-541) and a flipped upper-row cell (y 529-588) beside it would otherwise sit
    closer than the same-potential spacing (Magic 5 lambda, rule 1.NWL.S.1 1.25 um)."""
    xs = [nx for _, nx, _ in nands.values()]
    blk.paint("nwell", min(xs) - 6, Y_LROW + 67, max(xs) + 46, Y_MID + 53)


def draw_inputs(blk, nands):
    """Stubs from each NAND's A (PCK) and B (en<i>) to a metal3 track; returns {net: (track y, xmax)}."""
    tracks = {}
    lower = sorted(i for i in nands if not nands[i][0])
    upper = sorted(i for i in nands if nands[i][0])
    # B stubs of lower NANDs that sit under an upper NAND go down (they would meet its B stub)
    def overlaps(i, j):
        return abs(nands[i][1] - nands[j][1]) < 40 + 2 * SP
    low_a, low_b = list(LOW_TRACKS_A[1:]), list(LOW_TRACKS_B)
    up_a = list(UP_TRACKS_A[1:])
    tracks["PCK_low"] = LOW_TRACKS_A[0]
    tracks["PCK_up"] = UP_TRACKS_A[0]
    for i in lower:
        down = any(overlaps(i, j) for j in upper)
        tracks[f"en{i}"] = (low_b if down else low_a).pop(0)
    for i in upper:
        tracks[f"en{i}"] = up_a.pop(0)
    xmax = {}
    for i, (upper_, nx, pins) in nands.items():
        for pin, net, ty in (("A", "PCK", tracks["PCK_up" if upper_ else "PCK_low"]), ("B", f"en{i}", tracks[f"en{i}"])):
            x0, y0, x1, y1 = pins[pin]
            xc = nx + STUB_X["NAND2X1"][pin]
            # 4 lambda stub from inside the pin to the via pad centre
            if ty + 2 < y0:
                blk.r(net, "metal2", xc - 2, ty + 2, xc + 2, y0 + 1)
            else:
                blk.r(net, "metal2", xc - 2, y1 - 1, xc + 2, ty + 2)
            blk.via2(net, xc, ty + 2)
            key = net if net != "PCK" else ("PCK_up" if upper_ else "PCK_low")
            xmax[key] = max(xmax.get(key, 0), xc + 3.5)
    return tracks, xmax


def draw_west(blk, tracks, xmax, novl_tracks):
    """en pins -> jogs -> tracks; NG / PCK risers from the generator row."""
    for i in range(NCELL):
        xc, ye, ty = X_JOG[i], EN_Y[i], tracks[f"en{i}"]
        blk.r(f"en{i}", "metal3", 0, ye - 2, xc + 3.5, ye + 2)          # pin (control block height)
        blk.port(f"en{i}", "metal3", 0, ye - 2, 4, ye + 2)
        blk.via2(f"en{i}", xc, ye)
        blk.r(f"en{i}", "metal2", xc - 2, ty + 2, xc + 2, ye)
        blk.via2(f"en{i}", xc, ty + 2)
        blk.r(f"en{i}", "metal3", xc - 3.5, ty, xmax[f"en{i}"], ty + 4)
    blk.port("clk", "metal3", 0, NOVL_TRACKS[2], 4, NOVL_TRACKS[2] + 4)
    # PCK: generator track -> riser -> both PCK tracks
    y_pck = NOVL_TRACKS[novl_tracks["PCK"]] + 2
    blk.via2("PCK", X_PCK, y_pck)
    blk.r("PCK", "metal2", X_PCK - 2, y_pck, X_PCK + 2, tracks["PCK_up"] + 2)
    for key in ("PCK_low", "PCK_up"):
        ty = tracks[key]
        blk.via2("PCK", X_PCK, ty + 2)
        blk.r("PCK", "metal3", X_PCK - 3.5, ty, xmax[key], ty + 4)
    # NG: generator track -> riser -> both band rails
    y_ng = NOVL_TRACKS[novl_tracks["NG"]] + 2
    lo_rail, up_rail = band_y(False, RAIL["NG"]), band_y(True, RAIL["NG"])
    y_up = (up_rail[0] + up_rail[1]) / 2
    blk.via2("NG", X_NG, y_ng)
    blk.r("NG", "metal2", X_NG - 2, y_ng, X_NG + 2, y_up)
    blk.via2("NG", X_NG, (lo_rail[0] + lo_rail[1]) / 2)
    blk.via2("NG", X_NG, y_up)


# ---- power ------------------------------------------------------------------------------------------
def draw_power(blk):
    # rails of the two NAND rows over the whole width (gnd at 415 and 655, vdd at 535)
    for y, net in ((Y_LROW, "VSS"), (Y_MID, "VDD"), (Y_UROW, "VSS")):
        blk.r(net, "metal1", 126, y - 4, W, y + 4)
    # VDD riser from the bottom edge (S7 PVDD) to the generator's vdd rail and the rows' vdd rail
    blk.r("VDD", "metal2", X_VDD[0], 0, X_VDD[1], Y_MID + 4)
    for y in (120, Y_MID):
        for k in range(2):
            blk.via1("VDD", X_VDD[0] + 5 + 10 * k, y)
    blk.port("VDD", "metal2", X_VDD[0], 0, X_VDD[1], 4)
    blk.port("VSS", "metal1", W - 6, Y_LROW - 4, W, Y_LROW + 4)
    # VCD / VCR risers on the east edge, joining the rails of both bands
    lo_vcd, up_vcd = band_y(False, RAIL["VCD"]), band_y(True, RAIL["VCD"])
    lo_vcr, up_vcr = band_y(False, RAIL["VCR"]), band_y(True, RAIL["VCR"])
    xd = (X_VCD[0] + X_VCD[1]) / 2
    xr = (X_VCR[0] + X_VCR[1]) / 2
    blk.r("VCD", "metal2", X_VCD[0], lo_vcd[0] - 1.5, X_VCD[1], up_vcd[1] + 1.5)
    blk.via2("VCD", xd, (lo_vcd[0] + lo_vcd[1]) / 2)
    blk.via2("VCD", xd, (up_vcd[0] + up_vcd[1]) / 2)
    blk.r("VCR", "metal2", X_VCR[0], lo_vcr[0] - 1.5, X_VCR[1], up_vcr[1] + 1.5)
    blk.via2("VCR", xr, (lo_vcr[0] + lo_vcr[1]) / 2)
    blk.via2("VCR", xr, (up_vcr[0] + up_vcr[1]) / 2)
    blk.port("VCD", "metal2", X_VCD[0], lo_vcd[0], X_VCD[1], lo_vcd[0] + 4)
    blk.port("VCR", "metal2", X_VCR[0], 646, X_VCR[1], 650)


# ---- spacing check of the added routing ----------------------------------------------------------------
MIN_SP = {"metal1": 3, "metal2": SP, "metal3": SP}
CUTS = {"m2contact": ("metal1", "metal2"), "m3contact": ("metal2", "metal3")}


def spacing_errors(blk):
    """Added rectangles closer than MIN_SP to a rectangle of another net on the same metal (touching
    counts), including the kit cells' pins; the cells' own pin-to-pin gaps are the kit's."""
    by_layer = {}
    for kind, rects in (("route", blk.netrects), ("pin", blk.pinrects)):
        for net, layer, x0, y0, x1, y1 in rects:
            for m in CUTS.get(layer, (layer,)):
                if m in MIN_SP:
                    by_layer.setdefault(m, []).append((net, x0, y0, x1, y1, kind))
    errs = []
    for m, rs in by_layer.items():
        d = MIN_SP[m]
        rs.sort(key=lambda t: t[1])
        for k, a in enumerate(rs):
            for b in rs[k + 1:]:
                if b[1] >= a[3] + d:
                    break
                if a[0] == b[0] or (a[5] == "pin" and b[5] == "pin"):
                    continue
                dx = max(b[1] - a[3], a[1] - b[3], 0)
                dy = max(b[2] - a[4], a[2] - b[4], 0)
                if (dx * dx + dy * dy) ** 0.5 < d - 1e-9:
                    errs.append((m, a, b))
    return errs


# ---- structures ---------------------------------------------------------------------------------------
# Bottom structures hang under their pair (node column ND<i> comes down from y 341); their VSS goes up a
# metal1 strap at the left of the pair's slot to the lower row's gnd rail. Top structures sit over the
# upper band (ND<i> goes up from y 729); their ground straps go down to the upper row's gnd rail.
SLOT_STRAP = {8: 128, 9: 239, 6: 364, 7: 475}         # VSS strap x (6 lambda wide) of the west slots
GATE_Y = 150                                          # gate structures: active bottom
NAREA_Y, NEDGE_Y = 260, 270                           # N+ structures: diffusion bottom
PIP_UM = (258.0, 66.0)                                # PIP cell (KLayout) lower left, block um
COMB_X = (676, 856)                                   # comb x range; fingers 3 lambda, gaps 3 lambda
PLATE = {2: (140, 356), 3: (380, 616), 4: (626, 872)}  # top structures x range (outer plate)


def nd_x(i):
    band, x0 = PAIRS[i]
    return x0 + NODE_X["ND"][0], x0 + NODE_X["ND"][1]


def vss_strap(blk, x, y0, y1):
    blk.r("VSS", "metal1", x, y0, x + 6, y1)


def draw_gate(blk, i, gx, fingers, l):
    """NMOS gate structure: active bottom at GATE_Y, W 160 lambda; gate(s) to a contact under ND<i>.
    gx: active left. One finger: [S | gate l | D]; several: shared S/D tiles 17 lambda apart (l = 7)."""
    nd = f"ND{i}"
    w, y = 160, GATE_Y
    if fingers == 1:
        xa = gx + 6 + 2 + l + 2 + 6
        tiles = [gx, xa - 6]
        gates = [gx + 8]
    else:
        xa = gx + fingers * (l + 10) + 6
        tiles = [gx + (l + 10) * k for k in range(fingers + 1)]
        gates = [gx + (l + 10) * k + 8 for k in range(fingers)]
    blk.paint("ndiffusion", gx, y, xa, y + w)
    for t in tiles:
        blk.r("VSS", "ndcontact", t, y, t + 6, y + w)
        blk.r("VSS", "metal1", t, y - 10, t + 6, y + w)
    for g in gates:
        blk.paint("polysilicon", g, y - 2, g + l, y + w + 3)
    # gate bar over the tiles (metal1 tiles end at y + w; bar from y + w + 3), contact under ND<i>
    x0, x1 = nd_x(i)
    blk.paint("polysilicon", min(gates), y + w + 3, max(gates) + l, y + w + 9)
    blk.r(nd, "polycontact", x0, y + w + 3, x1, y + w + 9)
    blk.r(nd, "metal1", x0, y + w + 3, x1, Y_LROW - BAND_TOP)
    if not (min(gates) <= x0 and x1 <= max(gates) + l):
        raise SystemExit(f"cell {i}: gate contact not over the gates")
    # p+ taps both sides, VSS bar under the active, strap to the lower row's gnd rail
    left, right = gx - 10, xa + 4
    blk.r("VSS", "psubstratepcontact", left, y, left + 6, y + w)
    blk.r("VSS", "psubstratepcontact", right, y, right + 6, y + w)
    blk.r("VSS", "metal1", left, y - 10, left + 6, y + w)
    blk.r("VSS", "metal1", right, y - 10, right + 6, y + w)
    xs = SLOT_STRAP[i]
    blk.r("VSS", "metal1", xs, y - 10, right + 6, y - 4)
    vss_strap(blk, xs, y - 10, Y_LROW)
    return left, right + 6


def draw_narea(blk, i, nx):
    """N+ diffusion 67 x 67 lambda (20.1 um), contact strip along its top, p+ tap strips 8 lambda away."""
    nd, y = f"ND{i}", NAREA_Y
    blk.paint("ndiffusion", nx, y, nx + 67, y + 67)
    blk.r(nd, "ndcontact", nx, y + 61, nx + 67, y + 67)
    x0, x1 = nd_x(i)
    blk.r(nd, "metal1", nx, y + 61, nx + 67, y + 67)
    blk.r(nd, "metal1", x0, y + 61, x1, Y_LROW - BAND_TOP)
    for t in (nx - 14, nx + 75):
        blk.r("VSS", "psubstratepcontact", t, y, t + 6, y + 67)
        blk.r("VSS", "metal1", t, y - 10, t + 6, y + 67)
    xs = SLOT_STRAP[i]
    blk.r("VSS", "metal1", xs, y - 10, nx + 81, y - 4)
    vss_strap(blk, xs, y - 10, Y_LROW)


def draw_nedge(blk, i, nx, n=14):
    """N+ fingers 3 x 50 lambda (0.9 x 15 um), 6 lambda apart (Magic's diffusion spacing, 1.8 um; rule
    document 2.ACT.S 1.0 um), joined by a contact strip on top."""
    nd, y = f"ND{i}", NEDGE_Y
    wtot = n * 9 - 6
    for k in range(n):
        blk.paint("ndiffusion", nx + 9 * k, y, nx + 9 * k + 3, y + 50)
    blk.r(nd, "ndcontact", nx, y + 50, nx + wtot, y + 56)
    blk.r(nd, "metal1", nx, y + 50, nx + wtot, y + 56)
    x0, x1 = nd_x(i)
    blk.r(nd, "metal1", x0, y + 50, x1, Y_LROW - BAND_TOP)
    for t in (nx - 14, nx + wtot + 8):
        blk.r("VSS", "psubstratepcontact", t, y, t + 6, y + 56)
        blk.r("VSS", "metal1", t, y - 10, t + 6, y + 56)
    xs = SLOT_STRAP[i]
    blk.r("VSS", "metal1", xs, y - 10, nx + wtot + 14, y - 4)
    vss_strap(blk, xs, y - 10, Y_LROW)


def draw_comb(blk, i):
    """Interdigitated metal1: VSS comb from the bottom (on the block's VSS edge), ND<i> comb from the top."""
    nd = f"ND{i}"
    xa, xb = COMB_X
    top = Y_BOT1 - 4
    blk.r("VSS", "metal1", xa, -4, xb, 6)
    blk.r(nd, "metal1", xa, top - 6, xb, top)
    k = 0
    while xa + 12 * k + 3 <= xb:
        blk.r("VSS", "metal1", xa + 12 * k, 6, xa + 12 * k + 3, top - 9)
        if xa + 12 * k + 9 <= xb:
            blk.r(nd, "metal1", xa + 12 * k + 6, 9, xa + 12 * k + 9, top - 6)
        k += 1
    x0, x1 = nd_x(i)
    blk.r(nd, "metal1", x0, top - 6, x1, Y_LROW - BAND_TOP)


def pip_um():
    """The 30 x 30 um PIP (PDK pipcap layer set), um from its lower left: {layer: [boxes]}."""
    a = 30.0
    p2 = (1.2, 1.2, 1.2 + a, 1.2 + a)
    out = {"NSD": [(0, 0, a + 4.4, a + 2.4)], "CAP": [(0, 0, a + 4.4, a + 2.4)],
           "POLY1": [(0.2, 0.2, a + 4.2, a + 2.2)], "POLY2": [p2], "LVSD": [(1.2, 1.2, 1.2 + a, 1.4)],
           "MET1": [(1.6, 1.6, a + 0.8, a + 0.8), (a + 2.0, 1.6, a + 3.8, a + 0.8)], "CONT": []}
    n = int((a - 2.2 - 0.6) // 1.2) + 1          # cuts 1.1 um inside the poly2 edge, 1.2 um pitch
    for ix in range(n):
        for iy in range(n):
            out["CONT"].append((2.3 + 1.2 * ix, 2.3 + 1.2 * iy, 2.9 + 1.2 * ix, 2.9 + 1.2 * iy))
    for iy in range(n):
        out["CONT"].append((a + 2.6, 2.3 + 1.2 * iy, a + 3.2, 2.9 + 1.2 * iy))
    return out


def draw_pip_leads(blk, i):
    """Magic side of the PIP: node lead onto its top-plate metal1, VSS lead from its poly1 strip."""
    px, py = (v / LAMBDA_UM for v in PIP_UM)
    a = 30.0 / LAMBDA_UM
    x0, x1 = nd_x(i)
    top_m1 = py + (30.0 + 0.8) / LAMBDA_UM
    blk.r(f"ND{i}", "metal1", x0, round((top_m1 - 8) * 2) / 2, x1, Y_LROW - BAND_TOP)
    sx0, sx1 = px + 32.0 / LAMBDA_UM, px + 33.8 / LAMBDA_UM
    blk.r("VSS", "metal1", round(sx0 * 2) / 2, -4, round(sx1 * 2) / 2 - 0.5,
          round((py + 1.6 / LAMBDA_UM + 8) * 2) / 2)
    return a


def draw_plates(blk):
    # cell 2: MET1 plate over field, p+ tap strip on its left (strap down to the upper gnd rail)
    xa, xb = PLATE[2]
    nd = "ND2"
    blk.r(nd, "metal1", xa, Y_TOP0, xb, H - 4)
    x0, x1 = nd_x(2)
    blk.r(nd, "metal1", x0, Y_UROW + BAND_TOP, x1, Y_TOP0)
    blk.r("VSS", "psubstratepcontact", xa - 14, Y_TOP0, xa - 8, H - 4)
    blk.r("VSS", "metal1", xa - 14, Y_UROW, xa - 8, H - 4)
    # cell 3: MET2 plate over a MET1 plate at VSS
    xa, xb = PLATE[3]
    nd = "ND3"
    blk.r("VSS", "metal1", xa, Y_TOP0 + 4, xb, H - 4)
    blk.r(nd, "metal2", xa + 7, Y_TOP0 + 11, xb - 7, H - 11)
    x0, x1 = nd_x(3)
    blk.r(nd, "m2contact", x0 - 0.5, Y_UROW + BAND_TOP - 7, x1 + 0.5, Y_UROW + BAND_TOP)
    blk.r(nd, "metal2", x0 - 0.5, Y_UROW + BAND_TOP - 7, x1 + 0.5, Y_TOP0 + 11)
    vss_strap(blk, xa, Y_UROW, Y_TOP0 + 4)
    # cell 4: MET3 plate over a MET2 plate at VSS
    xa, xb = PLATE[4]
    nd = "ND4"
    blk.r("VSS", "metal2", xa, Y_TOP0 + 12, xb, H - 4)
    blk.r(nd, "metal3", xa + 7, Y_TOP0 - 3, xb - 7, H - 11)
    x0, x1 = nd_x(4)
    blk.r(nd, "m2contact", x0 - 0.5, Y_UROW + BAND_TOP - 7, x1 + 0.5, Y_UROW + BAND_TOP)
    blk.r(nd, "metal2", x0 - 0.5, Y_UROW + BAND_TOP - 7, x1 + 0.5, Y_TOP0 + 5)
    blk.r(nd, "m3contact", x0 - 0.5, Y_TOP0 - 2, x1 + 0.5, Y_TOP0 + 5)
    blk.r("VSS", "metal2", xa, Y_UROW - 3.5, xa + 7, Y_TOP0 + 12)
    blk.via1("VSS", xa + 3.5, Y_UROW)


# ---- assembly of the block ------------------------------------------------------------------------------
NAND_NETS = {"A": "PCK", "B": "en{i}", "Y": "PG{i}"}


def build():
    blk = Block(NAME)
    # generator row and its pins
    track_of, x_end = draw_novl(blk)
    pin_net = {(inst, pin): net for net, pins in novl_nets().items() for inst, pin in pins}
    x = X_NOVL
    for inst, cell in NOVL_CELLS:
        for pin, (a, b, c, d) in PINS[cell].items():
            blk.pinrects.append((pin_net[(inst, pin)], "metal2", x + a, b, x + c, d))
        x += CELL_W[cell]
    # pairs, gates and their inputs
    nands = draw_pairs_and_gates(blk)
    draw_row_well(blk, nands)
    for i, (upper, nx, pins) in nands.items():
        for pin, rect in pins.items():
            blk.pinrects.append((NAND_NETS[pin].format(i=i), "metal2", *rect))
    draw_band_rails(blk)
    tracks, xmax = draw_inputs(blk, nands)
    draw_west(blk, tracks, xmax, track_of)
    draw_power(blk)
    # structures
    draw_gate(blk, 8, 165, 1, round(GATE_L10[1] / LAMBDA_UM))
    draw_gate(blk, 9, 259, GATE_L2[2], round(GATE_L2[1] / LAMBDA_UM))
    draw_narea(blk, 6, 389)
    draw_nedge(blk, 7, 500)
    draw_comb(blk, 5)
    draw_pip_leads(blk, 1)
    draw_plates(blk)
    # bottom stubs of the lower pairs end at y 341: nothing to add; top: NR stubs end at 729
    return blk, dict(tracks=tracks, novl_tracks=track_of, novl_end=x_end)


def pins_json(blk):
    um = lambda v: round(v * LAMBDA_UM, 3)
    pins = {name: {"layer": layer, "box": [um(x0), um(y0), um(x1), um(y1)]}
            for name, layer, x0, y0, x1, y1 in blk.ports}
    rails = {"VSS_low_rail": [Y_LROW - 4, Y_LROW + 4], "VSS_up_rail": [Y_UROW - 4, Y_UROW + 4],
             "VSS_bottom": [-4, 4]}
    return {"cell": NAME, "unit": "um, block coordinates (origin: lower left)",
            "origin_die": list(ORIGIN_DIE), "size": [um(W), um(H)], "pins": pins,
            "rails": {k: [um(a), um(b)] for k, (a, b) in rails.items()},
            "pip": {"lower_left": list(PIP_UM), "size": [34.4, 32.4]},
            "structures": STRUCTURES}


def add_pip(gds_in: Path, gds_out: Path):
    """Insert the PIP (PDK pipcap layer set, ETRI layers) into the top cell of the Magic GDS."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(str(gds_in))
    top = ly.top_cell()
    ly.rename_cell(top.cell_index(), NAME)
    num = {"NSD": 14, "CAP": 53, "POLY1": 12, "POLY2": 13, "LVSD": 60, "MET1": 32, "CONT": 31}
    px, py = PIP_UM
    for name, boxes in pip_um().items():
        li = ly.layer(num[name], 0)
        for a, b, c, d in boxes:
            top.shapes(li).insert(kdb.DBox(px + a, py + b, px + c, py + d))
    ly.write(str(gds_out))


def flat_drc(out: Path):
    """Magic DRC of a flattened copy: the hierarchical check also reports the kit cells' rails that
    abut or overlap ("This layer can't abut or partially overlap between subcells"), which the kit's
    drc_core.sh ignores and which disappear when flattened (as for the control block, teg_ctrl_F)."""
    script = f"""drc off
load {NAME} -force
flatten {NAME}_flat
load {NAME}_flat
select top cell
drc on
drc check
drc catchup
set n [drc list count total]
puts "FLATDRC $n"
foreach {{why boxes}} [drc listall why] {{ puts "FLATWHY [llength $boxes] {{$why}}" }}
"""
    run_magic(script, out, f"{NAME}_flatdrc.log")
    txt = (out / f"{NAME}_flatdrc.log").read_text()
    m = re.search(r"^FLATDRC (\d+)", txt, re.M)
    return (int(m.group(1)) if m else -1), re.findall(r"^FLATWHY (.*)$", txt, re.M)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--netlist-only", action="store_true")
    args = ap.parse_args(argv)
    out = args.out
    (out / "sch").mkdir(parents=True, exist_ok=True)
    (out / "sch" / f"{NAME}.spice").write_text(netlist())
    if args.netlist_only:
        print(f"wrote {out / 'sch' / (NAME + '.spice')}")
        return 0
    blk, info = build()
    errs = spacing_errors(blk)
    for m, a, b in errs[:30]:
        print(f"  spacing {m}: {a} -- {b}")
    if errs:
        sys.exit(f"{len(errs)} spacing errors in the added routing")
    for ext in (".mag", ".ext", ".spice", ".gds"):
        (out / f"{NAME}{ext}").unlink(missing_ok=True)
    # The GDS comes from a flattened copy, as the kit writes its cores (mag2gds.sh): placed as cells, the
    # standard cells' rail taps and the pairs' taps generate their contact cuts separately and overlap.
    (out / f"{NAME}_flat.gds").unlink(missing_ok=True)
    run_magic(blk.magic_tcl() + f"flatten {NAME}_flat\nload {NAME}_flat\ncif ostyle lambda=0.30(ETRI)\n"
              f"gds write {NAME}_flat.gds\n", out, f"{NAME}_build.log")
    if not (out / f"{NAME}_flat.gds").exists():
        sys.exit(f"Magic did not write {NAME}_flat.gds (see {out / (NAME + '_build.log')})")
    add_pip(out / f"{NAME}_flat.gds", out / f"{NAME}_full.gds")
    (out / f"{NAME}_pins.json").write_text(json.dumps(pins_json(blk), indent=1))
    x0, y0, x1, y1 = blk.bbox()
    print(f"{NAME}: {(x1 - x0) * LAMBDA_UM:.1f} x {(y1 - y0) * LAMBDA_UM:.1f} um, {len(blk.rects)} rectangles, "
          f"{len(blk.cells)} standard cells, {len(blk.ports)} ports; {NAME}_full.gds adds the PIP")
    if args.check:
        n, why = flat_drc(out)
        print(f"  Magic DRC, flattened: {n}" + "".join(f"\n    {w}" for w in why))
        ok, line = etri_check(NAME, str(out / "sch" / f"{NAME}.spice"), out)
        print("  " + line + "   (hierarchical Magic DRC counts the kit cells' abutting rails)")
        return 0 if (ok or "LVS MATCH" in line) and n == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
