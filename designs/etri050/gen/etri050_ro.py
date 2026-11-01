#!/usr/bin/env python3
"""RO bank of pdkv (plan "4. RO 뱅크"): INV, NAND, NOR, wire and poly2-resistor ring oscillators.

Every RO has 31 stages. Stage 0 is NAND2X1(A = stage 30, B = ro_en<i>): a stopped RO holds a known
state and starts in its fundamental mode (with a free start the NAND RO can lock into its third
harmonic, plan simulation). A tap INVX1 -> INVX4 on stage 0's output drives ro_in<i> of the control
block, which picks one RO (rosel) and divides it by 256 onto OUT.

  index 0  inv   stages 1-30 INVX1
  index 1  nand  stages 1-30 NAND2X1, B at VDD
  index 2  nor   stages 1-30 NOR2X1, B at VSS
  index 4  wire  stages 1-30 INVX1, and every stage's output (0-30) carries a metal1 serpentine
                 0.9 um wide, three 99.6 um legs (about 307 um) over field: the plan's 300 um MET1 load
  index 5  res   stages 1-30 INVX1, each followed by a poly2 resistor W 2 x L 80 um (40 squares, PDK
                 p2res layer set) to the next stage's input: block rores, below

Indices 0-2 and 4 form the block robank. With the wire RO's metal it fills the place left for it
(x 856-1210, y 823-1146 um on the die). The resistor RO is the block rores in the free strip above the
heater's return line (x 932-1405, y 1160-1297 um). The plan's FO4 RO (index 3) needs four more rows and
fits nowhere on the chip; the plan drops it first when area is short ("게이트 용량은 CBCM이 직접 잼").
Its control-block ports stay as they are (ro_en3 an unconnected output, ro_in3 tied to VSS).

Layout (lambda = 0.3 um, block origin = lower left, die (856.0, 826.0)): six standard-cell rows of
120 lambda, odd rows flipped so that neighbours share a rail (gnd at y 0, 240, 480, 720; vdd at 120,
360, 600):
  row 0  inv RO, interleaved (S15 S16 S14 ... S1 S30 S0 from the west): connections span <= 2 cells
  rows 1-2  nand RO folded: S15..S0 in row 1, S16..S30 above them in row 2; the turn (S15 -> S16,
         west end) and the closure (S30 -> S0, east end) cross the shared gnd rail in metal2
  rows 3-4  nor RO folded the same way
  row 5  wire RO, interleaved; the serpentines stand above it
Stage 0 and the tap sit at the east end of each RO, next to the channel. Connections run on metal3 tracks over the
cells with metal2 stubs to the pins (pads 4 lambda clear of the pins, tracks 9 lambda apart). ro_en
and ro_in go to an east channel of eight metal2 lines that leave the block's bottom edge; the chip
routes them to the control block's top-edge pins. VDD comes up a metal1 strap at the west edge that
joins the vdd rails; VSS joins the gnd rails through a metal2 strap with a via1 on each.

rores (die origin (932.0, 1166.0)): one flipped row (vdd rail at y 0, gnd rail at y 120) in the
interleaved order S15 S16 S14 ... S1 S30 S0, taps. Over every INVX1 stage s stands its resistor, upright
over field above the gnd rail: a metal2 riser takes the stage's output m5_<s> from its Y pin to a via1
on the resistor's bottom head; from the top head a via1, a metal2 bar and a metal2 return line in the
east part of the stage's cell (no pins there) come down to a metal3 track over the row, and a stub goes
into the next stage's A pin (r5_<s>). The stage is the plan's "INVX1 + poly2 40 sq" with the load
after the resistor, as in the plan's simulation, but heavier: the wiring of r5_<s> (the metal2 return
line, the next stage's input poly over field, track and stubs) is 19.6-22.4 fF against the plan's 5 fF,
and the resistor body adds its own capacitance, so the ring runs at about half the plan's frequency
(sim/blocks/ro_post.py, ro/README.md). Its response to the sheet resistance stays the plan's
(110 / 140 ohm/sq: +5.9 / -5.3 %, plan +5.8 / -5.2 %).
Magic draws the heads as a black-box cell p2r40 (ports A bottom, B top, property LEFview: Netgen
compares it as a two-pin subcircuit, so the ring order is checked); KLayout then adds the resistor
itself (POLY2, CONT, RES, LVSD, MET1 heads; the PDK p2res geometry with L = 80 um) into Magic's
flattened GDS, and --check extracts that GDS at device level as well (ro/rores_lvs.py: transistors
and 30 resistors of 5000 ohm against the circuit above).

usage: python3 designs/etri050/gen/etri050_ro.py [--block robank|rores|all] [--check] [--netlist-only]
       -> designs/etri050/ro/build/robank.mag, robank_flat.gds, sch/robank.spice, robank_pins.json,
          rores.mag, p2r40.mag, rores_flat.gds (Magic), rores_full.gds (with the resistors),
          sch/rores.spice, rores_pins.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

from etri050_mos import REPO, etri_check, run_magic
import etri050_cbcm as cb
from etri050_cbcm import Block, CELL_W, LAMBDA_UM, PINS, STUB_X

NAME = "robank"
DEFAULT_OUT = REPO / "designs/etri050/ro/build"
ORIGIN_DIE = (856.0, 826.0)
W, H = 1180, 1066
NST = 31
KINDS = {0: "inv", 1: "nand", 2: "nor", 4: "wire"}
STAGE_CELL = {"inv": "INVX1", "nand": "NAND2X1", "nor": "NOR2X1", "wire": "INVX1", "res": "INVX1"}
ROWS = 6
X0 = 66                                   # first cell of every row
VDD_STRAP = (4, 26)                       # metal1, west edge: joins the vdd rails, chip VDD at its bottom
GND_X0 = 32                               # gnd rails start east of the VDD strap
VSS_STRAP = (34, 44)                      # metal2 over the rails, a via1 on every gnd rail
RAIL_X1 = 1090                            # rails end west of the channel
CHANNEL = ["en0", "en1", "en2", "en4", "in0", "in1", "in2", "in4"]
CH_X = {n: 1094 + 11 * k for k, n in enumerate(CHANNEL)}    # channel line x0 (4 lambda wide, pads 3.5 clear)
PORT_Y = -10                              # channel lines and the VDD strap reach down to here
TRACKS_N = [77, 86, 95, 104, 113]         # normal rows: track y over the pins (pin tops <= 68.5)
TRACKS_F = [42, 33, 24, 15, 6]            # flipped rows: track y under the pins (pin bottoms >= 51.5)
LEG_PITCH, LEG_W = 10, 3                  # wire RO serpentine: legs 3 lambda wide, 10 lambda apart
LEG_Y0, LEG_Y1 = 728, H - 6               # legs from above the top gnd rail (y 716-724) to the top


def row_y(r):
    return 120 * r


def flipped(r):
    return r % 2 == 1


# ==== circuit =======================================================================================
def stage_nets(i, kind):
    """Instances of RO i: [(inst, cell, {pin: net})], stage outputs r<i>_<s>. In the resistor RO the
    inverter of stage s drives m<i>_<s> and its resistor (resistor_nets) gives r<i>_<s>."""
    n = lambda s: f"r{i}_{s % NST}"
    out = [(f"XS{i}_0", "NAND2X1", {"A": n(NST - 1), "B": f"en{i}", "Y": n(0)})]
    for s in range(1, NST):
        cell = STAGE_CELL[kind]
        pins = {"A": n(s - 1), "Y": f"m{i}_{s}" if kind == "res" else n(s)}
        if kind == "nand":
            pins["B"] = "VDD"
        elif kind == "nor":
            pins["B"] = "VSS"
        out.append((f"XS{i}_{s}", cell, pins))
    out.append((f"XT{i}a", "INVX1", {"A": n(0), "Y": f"t{i}"}))
    out.append((f"XT{i}b", "INVX4", {"A": f"t{i}", "Y": f"in{i}"}))
    return out


def resistor_nets(i):
    """Resistors of the resistor RO: [(inst, {A: stage output m<i>_<s>, B: next stage's input r<i>_<s>})]."""
    return [(f"XR{i}_{s}", {"A": f"m{i}_{s}", "B": f"r{i}_{s}"}) for s in range(1, NST)]


def netlist(with_cells: bool = True) -> str:
    """Schematic netlist of the block, written from the circuit above (not from the drawing)."""
    ports = CHANNEL + ["VDD", "VSS"]
    out = [f"* {NAME}: RO bank, ROs {', '.join(f'{i} {k}' for i, k in KINDS.items())} (see etri050_ro.py)"]
    if with_cells:
        out.append(cb.kit_stdcells_spice())
    out.append(f".subckt {NAME} " + " ".join(ports))
    order = {"INVX1": "A Y", "INVX4": "A Y", "NAND2X1": "A B Y", "NOR2X1": "A B Y"}
    for i, kind in KINDS.items():
        for inst, cell, pins in stage_nets(i, kind):
            out.append(f"{inst} " + " ".join(pins[p] for p in order[cell].split()) + f" VDD VSS {cell}")
    out.append(".ends")
    return "\n".join(out) + "\n"


# ==== placement =====================================================================================
def interleaved(i, kind):
    """Single-row order from the west: S15 S16 S14 S17 ... S1 S30 S0, then the taps (each connection
    spans at most two cells; stage 0, its enable and the tap sit at the east end, next to the channel)."""
    insts = {inst: (cell, pins) for inst, cell, pins in stage_nets(i, kind)}
    order = []
    for k in range(16):
        order.append(f"XS{i}_{k}")
        if k < 15:
            order.append(f"XS{i}_{NST - 1 - k}")
    order = order[::-1] + [f"XT{i}a", f"XT{i}b"]
    return [(inst, *insts[inst]) for inst in order]


def folded(i, kind):
    """Two rows from the west: [S15 .. S0, taps] and [S16 .. S30] above it (S16 over S15, S30 over S1)."""
    insts = {inst: (cell, pins) for inst, cell, pins in stage_nets(i, kind)}
    lower = [f"XS{i}_{s}" for s in range(15, -1, -1)] + [f"XT{i}a", f"XT{i}b"]
    upper = [f"XS{i}_{s}" for s in range(16, NST)]
    return [(n, *insts[n]) for n in lower], [(n, *insts[n]) for n in upper]


def place_row(blk, r, cells, x_start, where, at=None):
    """Cells side by side from x_start; at = {inst: x} places a cell at a given x instead."""
    x = x_start
    for inst, cell, pins in cells:
        x = (at or {}).get(inst, x)
        p = blk.cell(cell, x, row_y(r), flipped(r), inst)
        where[inst] = dict(cell=cell, x=x, row=r, pins=p, nets=pins)
        for pin, rect in p.items():
            blk.pinrects.append((pins[pin], "metal2", *rect))
        x += CELL_W[cell]
    return x


def placement(blk):
    where, ends = {}, {}
    ends[0] = place_row(blk, 0, interleaved(0, "inv"), X0, where)
    # folded ROs: the upper row starts 10 lambda east and S30 sits 10 lambda west of S0, so that the
    # turn (S15 Y -> S16 A) and the closure (S30 Y -> S0 A) are straight metal2 lines across the rail
    for i, r in ((1, 1), (2, 3)):
        lo, up = folded(i, KINDS[i])
        ends[r] = place_row(blk, r, lo, X0, where)
        ends[r + 1] = place_row(blk, r + 1, up, X0 + 10, where, at={f"XS{i}_30": where[f"XS{i}_0"]["x"] - 10})
    ends[5] = place_row(blk, 5, interleaved(4, "wire"), X0, where)
    for r, e in ends.items():
        if e > RAIL_X1 - 4:
            raise SystemExit(f"row {r} ends at {e}, past the rails ({RAIL_X1})")
    return where, ends


# ==== routing =======================================================================================
def stub(blk, net, w, pin, ty):
    """4 lambda metal2 stub from inside the pin to a via2 on the track at ty; returns the via x."""
    x0, y0, x1, y1 = w["pins"][pin]
    xc = w["x"] + STUB_X[w["cell"]][pin]
    if ty + 2 > y1:
        blk.r(net, "metal2", xc - 2, y1 - 1, xc + 2, ty + 2)
    else:
        blk.r(net, "metal2", xc - 2, ty + 2, xc + 2, y0 + 1)
    blk.via2(net, xc, ty + 2)
    return xc


def cross_rail(blk, net, wa, pa, wb, pb):
    """Net between a pin of a flipped row (wa) and a pin of the normal row above it (wb), across their
    shared gnd rail: metal2 up from wa's pin, along the rail, up into wb's pin (stub-wide, 4 lambda)."""
    ya = wa["pins"][pa][3]
    yb = wb["pins"][pb][1]
    rail = row_y(wb["row"])
    xa = wa["x"] + STUB_X[wa["cell"]][pa]
    xb = wb["x"] + STUB_X[wb["cell"]][pb]
    blk.r(net, "metal2", xa - 2, ya - 1, xa + 2, rail + 2)
    blk.r(net, "metal2", min(xa, xb) - 2, rail - 2, max(xa, xb) + 2, rail + 2)
    blk.r(net, "metal2", xb - 2, rail - 2, xb + 2, yb + 1)


def route(blk, where):
    """Every net: metal3 track(s) in its row(s), or a metal2 crossing for the folded ROs' turns."""
    nets = {}
    for inst, w in where.items():
        for pin, net in w["nets"].items():
            nets.setdefault(net, []).append((inst, pin))
    done = set()
    # folded ROs: turn S15 -> S16 and closure S30 -> S0 across the shared rail
    for i in (1, 2):
        for src, dst in ((f"XS{i}_15", f"XS{i}_16"), (f"XS{i}_30", f"XS{i}_0")):
            net = where[src]["nets"]["Y"]
            wa, wb = where[src], where[dst]
            if flipped(wa["row"]):
                cross_rail(blk, net, wa, "Y", wb, "A")
            else:
                cross_rail(blk, net, wb, "A", wa, "Y")
            done.add(net)
    # tracks per row: left-edge assignment. en / in run on to their channel line; the B inputs tied to
    # VDD or VSS gather on a track per row that ends on the west straps (the kit cells' rails are tap
    # contacts all along, and the rule document allows no via1 on a contact)
    busy = {r: {t: [] for t in range(len(TRACKS_N))} for r in range(ROWS)}
    tracks = {}
    plan = []
    for net, pins in nets.items():
        if net in done:
            continue
        by_row = {}
        for inst, pin in pins:
            by_row.setdefault(where[inst]["row"], []).append((inst, pin))
        if len(by_row) != 1 and net not in ("VDD", "VSS"):
            raise SystemExit(f"net {net} spans rows {sorted(by_row)} without a crossing")
        for r, rp in by_row.items():
            xs = [where[inst]["x"] + STUB_X[where[inst]["cell"]][pin] for inst, pin in rp]
            if net in CH_X:
                xs.append(CH_X[net] + 2)
            elif net == "VSS":
                xs.append((VSS_STRAP[0] + VSS_STRAP[1]) / 2)
            elif net == "VDD":
                xs.append((VDD_STRAP[0] + VDD_STRAP[1]) / 2)
            plan.append((min(xs) - 3.5, max(xs) + 3.5, net, r, rp))
    for lo, hi, net, r, pins in sorted(plan, key=lambda p: (p[1] - p[0] < 600, p[0])):
        for t in range(len(TRACKS_N)):
            if all(hi + cb.SP <= a or lo >= b + cb.SP for a, b in busy[r][t]):
                busy[r][t].append((lo, hi))
                tracks[(net, r)] = t
                break
        else:
            raise SystemExit(f"row {r}: no track for {net}")
        ty = row_y(r) + (TRACKS_F if flipped(r) else TRACKS_N)[t]
        blk.r(net, "metal3", lo, ty, hi, ty + 4)
        for inst, pin in pins:
            stub(blk, net, where[inst], pin, ty)
        if net in CH_X:
            x = CH_X[net]
            blk.via2(net, x + 2, ty + 2)
            blk.r(net, "metal2", x, PORT_Y, x + 4, ty + 5.5)
            blk.port(net, "metal2", x, PORT_Y, x + 4, PORT_Y + 4)
        elif net == "VSS":              # via2 onto the metal2 VSS strap
            blk.via2(net, (VSS_STRAP[0] + VSS_STRAP[1]) / 2, ty + 2)
        elif net == "VDD":              # via2, metal2 up 12 lambda, via1 onto the metal1 VDD strap
            xc = (VDD_STRAP[0] + VDD_STRAP[1]) / 2
            blk.via2(net, xc, ty + 2)
            blk.r(net, "metal2", xc - 3.5, ty + 2, xc + 3.5, ty + 17.5)
            blk.via1(net, xc, ty + 14)
    return tracks


# ==== power, wells, wire serpentines =================================================================
def power(blk, ends):
    for r in range(ROWS + 1):
        y = row_y(r)
        if r % 2 == 0:          # gnd rail
            blk.r("VSS", "metal1", GND_X0, y - 4, RAIL_X1, y + 4)
            blk.via1("VSS", (VSS_STRAP[0] + VSS_STRAP[1]) / 2, y)
        else:
            blk.r("VDD", "metal1", VDD_STRAP[0], y - 4, RAIL_X1, y + 4)
    blk.r("VDD", "metal1", VDD_STRAP[0], PORT_Y, VDD_STRAP[1], row_y(ROWS - 1) + 4)
    blk.r("VSS", "metal2", VSS_STRAP[0], -4, VSS_STRAP[1], row_y(ROWS) + 4)
    blk.port("VDD", "metal1", VDD_STRAP[0], PORT_Y, VDD_STRAP[1], PORT_Y + 4)
    blk.port("VSS", "metal1", 900, -4, 960, 4)


def wells(blk, where):
    """One N-well around each shared vdd rail over the cells of both rows: the wells of a normal cell and
    of the flipped cell above it would otherwise sit closer than the same-potential spacing."""
    for r in range(0, ROWS, 2):
        xs = [(w["x"], w["x"] + CELL_W[w["cell"]]) for w in where.values() if w["row"] in (r, r + 1)]
        y = row_y(r + 1)
        blk.paint("nwell", min(a for a, _ in xs) - 6, y - 53, max(b for _, b in xs) + 6, y + 53)


def serpentines(blk, where):
    """Wire RO: from each stage output a metal2 riser to a via1 above the top gnd rail, then a metal1
    serpentine of three legs (up, down, up) 10 lambda apart."""
    for inst, w in where.items():
        if w["row"] != ROWS - 1 or not inst.startswith("XS"):
            continue
        net = w["nets"]["Y"]
        xc = w["x"] + STUB_X[w["cell"]]["Y"]
        blk.r(net, "metal2", xc - 2, w["pins"]["Y"][3] - 1, xc + 2, LEG_Y0 + 7)
        blk.via1(net, xc, LEG_Y0 + 3.5)
        legs = [xc - 1.5 + LEG_PITCH * k for k in range(3)]
        for x in legs:
            blk.r(net, "metal1", x, LEG_Y0, x + LEG_W, LEG_Y1)
        blk.r(net, "metal1", legs[0], LEG_Y1 - LEG_W, legs[1] + LEG_W, LEG_Y1)
        blk.r(net, "metal1", legs[1], LEG_Y0, legs[2] + LEG_W, LEG_Y0 + LEG_W)


def build():
    blk = Block(NAME)
    where, ends = placement(blk)
    wells(blk, where)
    power(blk, ends)
    tracks = route(blk, where)
    serpentines(blk, where)
    return blk, dict(where=where, ends=ends, tracks=tracks)


# ==== resistor RO (control-block index 5): the block rores ============================================
RES_NAME = "rores"
RES_I = 5
RES_ORIGIN_DIE = (932.0, 1166.0)
RCELL = "p2r40"                 # Magic black box of one resistor: its two metal1 heads, ports A and B
RPAD_W = 7                      # pads 7 lambda wide, centred on the stage's Y stub (cell x + 15)
RPAD_A = (0, 13)                # bottom pad (cell y): via1 tile 0-7, head 7-13 over the contact
RPAD_B = (275.5, 289)           # top pad: head over the contact, via1 tile 282-289
R_Y0 = 128                      # resistor cell origin y: 4 lambda over the gnd rail (116-124)
RES_TRACKS = [94, 104, 114, 42, 32, 22, 12, 2]  # flipped row, 10 lambda apart (via2 tiles 9.5 apart in x
                                                 # on neighbouring tracks): over the pins, then under
RES_RET_DX = 24                 # return line centre from the stage cell's x (INVX1 pins end at x + 18.5)
RES_RAIL_X1 = 1080              # rails end 4 lambda past the last cell (x 1076)
RES_CH_X = {"in5": 1084, "en5": 1095}            # in5 west of en5: the chip route nests the two
RES_PORT_Y = -14                # channel lines and straps reach down to here (well bottom -6)
RES_W, RES_H = 1101, 417


def p2r_um():
    """One poly2 resistor W 2 x L 80 um (40 squares) with the layer set of the PDK p2res cell
    (analog_ETRI/GDS/NSPL_0p5um.gds, W 2 x L 100 um): POLY2 body, RES 0.8 um around it, LVSD between
    the contacts (sets L, full RES width), one 0.6 um contact per end against the LVSD edge (0.6 um from
    the POLY2 end, 0.7 um from its sides), MET1 head 1.8 um. Turned upright; {layer: [boxes]}, um in the
    p2r40 cell (the POLY2 starts at the top of the bottom pad's via1 tile, y 2.1)."""
    xc, yb = RPAD_W / 2 * LAMBDA_UM, 7 * LAMBDA_UM
    box = lambda dx0, y0, dx1, y1: (round(xc + dx0, 3), round(yb + y0, 3), round(xc + dx1, 3), round(yb + y1, 3))
    return {"POLY2": [box(-1.0, 0.0, 1.0, 82.4)],
            "CONT": [box(-0.3, 0.6, 0.3, 1.2), box(-0.3, 81.2, 0.3, 81.8)],
            "MET1": [box(-1.0, 0.0, 1.0, 1.8), box(-1.0, 80.6, 1.0, 82.4)],
            "LVSD": [box(-1.8, 1.2, 1.8, 81.2)],
            "RES": [box(-1.8, -0.8, 1.8, 83.2)]}


def rcell_tcl() -> str:
    """Magic script for the black box p2r40: a metal1 pad per head (ports A, B), abstract view."""
    a0, a1 = RPAD_A
    b0, b1 = RPAD_B
    return "\n".join([f"load {RCELL} -force", "snap internal",
                      f"box 0um {um(a0)} {um(RPAD_W)} {um(a1)}", "paint metal1", "label A c metal1",
                      "port make 1",
                      f"box 0um {um(b0)} {um(RPAD_W)} {um(b1)}", "paint metal1", "label B c metal1",
                      "port make 2", "property LEFview TRUE", f"save {RCELL}"]) + "\n"


def um(v):
    return f"{v * LAMBDA_UM:.2f}um"


def res_netlist(with_cells: bool = True) -> str:
    """Schematic netlist of rores; the resistors are the two-pin black box p2r40 (as Magic extracts them)."""
    out = [f"* {RES_NAME}: resistor RO (index {RES_I}), see etri050_ro.py"]
    if with_cells:
        out.append(cb.kit_stdcells_spice())
    out += [f".subckt {RCELL} A B", ".ends",
            f".subckt {RES_NAME} en{RES_I} in{RES_I} VDD VSS"]
    order = {"INVX1": "A Y", "INVX4": "A Y", "NAND2X1": "A B Y"}
    for inst, cell, pins in stage_nets(RES_I, "res"):
        out.append(f"{inst} " + " ".join(pins[p] for p in order[cell].split()) + f" VDD VSS {cell}")
    for inst, pins in resistor_nets(RES_I):
        out.append(f"{inst} {pins['A']} {pins['B']} {RCELL}")
    out.append(".ends")
    return "\n".join(out) + "\n"


def build_res():
    """The block rores: [Block, info]. info['res'][inst] = cell origin, centre x, return x, nets."""
    blk = Block(RES_NAME)
    where, res = {}, {}
    x = X0
    for inst, cell, pins in interleaved(RES_I, "res"):
        p = blk.cell(cell, x, 0, True, inst)
        where[inst] = dict(cell=cell, x=x, pins=p, nets=pins)
        for pin, rect in p.items():
            blk.pinrects.append((pins[pin], "metal2", *rect))
        x += CELL_W[cell]
    if x > RES_RAIL_X1 - 4:
        raise SystemExit(f"rores row ends at {x}, past the rails ({RES_RAIL_X1})")
    # resistors over their stages: riser to the bottom head, bar and return line from the top head
    yt = R_Y0 + RPAD_B[1] - 3.5
    for inst, nets in resistor_nets(RES_I):
        s = int(inst.rsplit("_", 1)[1])
        w = where[f"XS{RES_I}_{s}"]
        xc = w["x"] + STUB_X["INVX1"]["Y"]
        cx = xc - RPAD_W / 2
        xr = w["x"] + RES_RET_DX
        blk.cells.append((RCELL, cx, R_Y0, False, inst))
        blk.pinrects.append((nets["A"], "metal1", cx, R_Y0 + RPAD_A[0], cx + RPAD_W, R_Y0 + RPAD_A[1]))
        blk.pinrects.append((nets["B"], "metal1", cx, R_Y0 + RPAD_B[0], cx + RPAD_W, R_Y0 + RPAD_B[1]))
        blk.r(nets["A"], "metal2", xc - 2, w["pins"]["Y"][3] - 1, xc + 2, R_Y0 + 3.5)
        blk.via1(nets["A"], xc, R_Y0 + 3.5)
        blk.via1(nets["B"], xc, yt)
        blk.r(nets["B"], "metal2", xc - 3.5, yt - 3.5, xr + 2, yt + 3.5)
        res[inst] = dict(stage=s, x=cx, y=R_Y0, xc=xc, xr=xr, nets=nets)
    tracks = route_res(blk, where, res, yt)
    # power: vdd rail (y 0) from the VDD strap, gnd rail (y 120) with a via1 onto the VSS strap
    blk.r("VDD", "metal1", VDD_STRAP[0], -4, RES_RAIL_X1, 4)
    blk.r("VDD", "metal1", VDD_STRAP[0], RES_PORT_Y, VDD_STRAP[1], 4)
    blk.r("VSS", "metal1", GND_X0, 116, RES_RAIL_X1, 124)
    blk.r("VSS", "metal2", VSS_STRAP[0], RES_PORT_Y, VSS_STRAP[1], 124)
    blk.via1("VSS", (VSS_STRAP[0] + VSS_STRAP[1]) / 2, 120)
    blk.port("VDD", "metal1", VDD_STRAP[0], RES_PORT_Y, VDD_STRAP[1], RES_PORT_Y + 4)
    blk.port("VSS", "metal2", VSS_STRAP[0], RES_PORT_Y, VSS_STRAP[1], RES_PORT_Y + 4)
    return blk, dict(where=where, res=res, tracks=tracks, end=x)


def route_res(blk, where, res, yt):
    """Every signal net of rores on one metal3 track over the row (left-edge, tracks over the pins first):
    the return lines come down to their track from the top bar, the pins take stubs, en5 / in5 run on to
    their channel line and down to the block's bottom edge."""
    nets = {}
    for inst, w in where.items():
        for pin, net in w["nets"].items():
            if net not in ("VDD", "VSS"):
                nets.setdefault(net, []).append((inst, pin))
    ret = {r["nets"]["B"]: r["xr"] for r in res.values()}
    plan = []
    for net, pins in nets.items():
        if net.startswith(f"m{RES_I}_"):
            continue                                   # the riser, drawn with the resistor
        xs = [where[inst]["x"] + STUB_X[where[inst]["cell"]][pin] for inst, pin in pins]
        if net in ret:
            xs.append(ret[net])
        if net in RES_CH_X:
            xs.append(RES_CH_X[net] + 2)
        plan.append((min(xs) - 3.5, max(xs) + 3.5, net, pins))
    busy = {t: [] for t in RES_TRACKS}
    tracks = {}
    for lo, hi, net, pins in sorted(plan, key=lambda p: p[0]):
        if net in ret and len(pins) == 1 and hi - lo < 2 * 3.5 + 7 + cb.SP:
            # the turn S15 -> S16: the return line and the next cell's A stub are 9.5 lambda apart, too
            # close for two via2 tiles (their GDS pads, 0.05 um smaller, leave a 0.75 um notch). One
            # metal2 jog over the pins joins them instead, without a track.
            (inst, pin), xr = pins[0], ret[net]
            w = where[inst]
            xs = w["x"] + STUB_X[w["cell"]][pin]
            yj = RES_TRACKS[0]
            blk.r(net, "metal2", min(xr, xs) - 2, yj, max(xr, xs) + 2, yj + 4)
            blk.r(net, "metal2", xr - 2, yj, xr + 2, yt)
            blk.r(net, "metal2", xs - 2, w["pins"][pin][3] - 1, xs + 2, yj + 4)
            tracks[net] = None
            continue
        for t in RES_TRACKS:
            if all(hi + cb.SP <= a or lo >= b + cb.SP for a, b in busy[t]):
                busy[t].append((lo, hi))
                tracks[net] = t
                break
        else:
            raise SystemExit(f"rores: no track for {net}")
        ty = tracks[net]
        blk.r(net, "metal3", lo, ty, hi, ty + 4)
        for inst, pin in pins:
            stub(blk, net, where[inst], pin, ty)
        if net in ret:
            xr = ret[net]
            blk.r(net, "metal2", xr - 2, ty + 2, xr + 2, yt)
            blk.via2(net, xr, ty + 2)
        if net in RES_CH_X:
            x = RES_CH_X[net]
            blk.via2(net, x + 2, ty + 2)
            blk.r(net, "metal2", x, RES_PORT_Y, x + 4, ty + 5.5)
            blk.port(net, "metal2", x, RES_PORT_Y, x + 4, RES_PORT_Y + 4)
        vx = sorted(xs_of(net, pins, where, ret))
        if any(0 < b - a < 7 + cb.SP for a, b in zip(vx, vx[1:])):
            raise SystemExit(f"rores: via2 tiles of {net} closer than the spacing on track {ty}: {vx}")
    return tracks


def xs_of(net, pins, where, ret):
    """Via2 x of a net on its track: the stubs, the return line, the channel line."""
    xs = [where[inst]["x"] + STUB_X[where[inst]["cell"]][pin] for inst, pin in pins]
    if net in ret:
        xs.append(ret[net])
    if net in RES_CH_X:
        xs.append(RES_CH_X[net] + 2)
    return xs


def add_resistors(gds_in: Path, gds_out: Path, info):
    """Insert the resistors (PDK p2res layer set, ETRI layer numbers) into Magic's flattened GDS."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(str(gds_in))
    top = ly.top_cell()
    ly.rename_cell(top.cell_index(), RES_NAME)
    num = {"POLY2": 13, "CONT": 31, "MET1": 32, "LVSD": 60, "RES": 51}
    for r in info["res"].values():
        ox, oy = r["x"] * LAMBDA_UM, r["y"] * LAMBDA_UM
        for name, boxes in p2r_um().items():
            li = ly.layer(num[name], 0)
            for a, b, c, d in boxes:
                top.shapes(li).insert(kdb.DBox(round(ox + a, 3), round(oy + b, 3), round(ox + c, 3), round(oy + d, 3)))
    ly.write(str(gds_out))


def check_resistors(gds: Path, info):
    """The resistors in the final GDS: 30 separate POLY2 bodies, each W 2.0 um with LVSD L 80.0 um
    (40 squares), RES over all of it, two contacts per body, each inside its own head pad (A at the
    bottom, B at the top, as LVS compared them), and no POLY2 or contact anywhere else. -> [problems]"""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    reg = lambda n: kdb.Region(top.begin_shapes_rec(ly.layer(n, 0))).merged()
    poly2, cont, lvsd, rmark, m1 = reg(13), reg(31), reg(60), reg(51), reg(32)
    dbu = ly.dbu
    bad = []
    bodies = list(poly2.each())
    if len(bodies) != len(info["res"]):
        bad.append(f"{len(bodies)} POLY2 bodies, {len(info['res'])} resistors drawn")
    found = set()
    for inst, r in sorted(info["res"].items()):
        ox, oy = r["x"] * LAMBDA_UM, r["y"] * LAMBDA_UM
        a, b, c, d = p2r_um()["POLY2"][0]
        box = kdb.DBox(ox + a, oy + b, ox + c, oy + d).to_itype(dbu)
        hit = [p for p in bodies if p.bbox() == box]
        if len(hit) != 1 or hit[0].num_points() != 4:
            bad.append(f"{inst}: no rectangular POLY2 body at {box}")
            continue
        found.add(hit[0].bbox().to_s())
        body = kdb.Region(hit[0])
        lv = (body & lvsd).bbox().to_dtype(dbu)
        sq = lv.height() / lv.width()
        if abs(lv.width() - R_W_UM) > 1e-6 or abs(lv.height() - R_L_UM) > 1e-6:
            bad.append(f"{inst}: LVSD part of the body {lv.width():.3f} x {lv.height():.3f} um")
        if not (body - rmark).is_empty():
            bad.append(f"{inst}: RES does not cover the body")
        cuts = [c.bbox().to_dtype(dbu) for c in (cont & body).each()]
        pads = {"A": kdb.DBox(ox, oy + RPAD_A[0] * LAMBDA_UM, ox + RPAD_W * LAMBDA_UM, oy + RPAD_A[1] * LAMBDA_UM),
                "B": kdb.DBox(ox, oy + RPAD_B[0] * LAMBDA_UM, ox + RPAD_W * LAMBDA_UM, oy + RPAD_B[1] * LAMBDA_UM)}
        if len(cuts) != 2:
            bad.append(f"{inst}: {len(cuts)} contacts on the body")
        for k, pad in pads.items():
            inside = [c for c in cuts if pad.contains(c.p1) and pad.contains(c.p2)]
            if len(inside) != 1:
                bad.append(f"{inst}: {len(inside)} contacts under head {k}")
            elif (kdb.Region(kdb.DBox(inside[0]).to_itype(dbu)) - m1).count():
                bad.append(f"{inst}: contact under head {k} not covered by metal1")
        r["squares"] = round(sq, 4)
    if len(found) != len(bodies):
        bad.append(f"{len(bodies) - len(found)} POLY2 shapes that are no resistor")
    if (cont & poly2).count() != 2 * len(info["res"]):
        bad.append(f"{(cont & poly2).count()} contacts on POLY2, {2 * len(info['res'])} expected")
    return bad


R_W_UM, R_L_UM = 2.0, 80.0


def res_pins_json(blk, info):
    um3 = lambda v: round(v * LAMBDA_UM, 3)
    pins = {name: {"layer": layer, "box": [um3(x0), um3(y0), um3(x1), um3(y1)]}
            for name, layer, x0, y0, x1, y1 in blk.ports}
    res = {inst: {"origin": [um3(r["x"]), um3(r["y"])], "A": r["nets"]["A"], "B": r["nets"]["B"]}
           for inst, r in sorted(info["res"].items(), key=lambda kv: kv[1]["stage"])}
    return {"cell": RES_NAME, "unit": "um, block coordinates (origin: lower left)",
            "origin_die": list(RES_ORIGIN_DIE), "size": [um3(RES_W), um3(RES_H - RES_PORT_Y)],
            "pins": pins, "vdd_rail": [um3(-4), um3(4)], "gnd_rail": [um3(116), um3(124)],
            "rail_x": [um3(GND_X0), um3(RES_RAIL_X1)], "resistor": {"cell": RCELL, "w_um": R_W_UM,
            "l_um": R_L_UM, "layers_um": p2r_um()}, "resistors": res}


# ==== outputs and checks =============================================================================
def pins_json(blk):
    um = lambda v: round(v * LAMBDA_UM, 3)
    pins = {name: {"layer": layer, "box": [um(x0), um(y0), um(x1), um(y1)]}
            for name, layer, x0, y0, x1, y1 in blk.ports}
    rails = {f"gnd{r}": [um(row_y(r) - 4), um(row_y(r) + 4)] for r in range(0, ROWS + 1, 2)}
    return {"cell": NAME, "unit": "um, block coordinates (origin: lower left)", "origin_die": list(ORIGIN_DIE),
            "size": [um(W), um(H)], "pins": pins, "gnd_rails": rails, "rail_x": [um(GND_X0), um(RAIL_X1)],
            "kinds": {str(i): k for i, k in KINDS.items()}}


def flat_drc(out: Path, name: str = NAME):
    """Magic DRC of a flattened copy (hierarchical checks count the kit cells' abutting rails)."""
    script = f"""drc off
load {name} -force
flatten {name}_flat
load {name}_flat
select top cell
drc on
drc check
drc catchup
set n [drc list count total]
puts "FLATDRC $n"
foreach {{why boxes}} [drc listall why] {{ puts "FLATWHY [llength $boxes] {{$why}}" }}
"""
    run_magic(script, out, f"{name}_flatdrc.log")
    txt = (out / f"{name}_flatdrc.log").read_text()
    m = re.search(r"^FLATDRC (\d+)", txt, re.M)
    return (int(m.group(1)) if m else -1), re.findall(r"^FLATWHY (.*)$", txt, re.M)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--block", choices=["robank", "rores", "all"], default="all")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--netlist-only", action="store_true")
    args = ap.parse_args(argv)
    rc = 0
    if args.block in ("robank", "all"):
        rc |= make_robank(args)
    if args.block in ("rores", "all"):
        rc |= make_rores(args)
    return rc


def make_rores(args) -> int:
    out = args.out
    (out / "sch").mkdir(parents=True, exist_ok=True)
    (out / "sch" / f"{RES_NAME}.spice").write_text(res_netlist())
    if args.netlist_only:
        return 0
    blk, info = build_res()
    errs = cb.spacing_errors(blk)
    for m, a, b in errs[:30]:
        print(f"  spacing {m}: {a} -- {b}")
    if errs:
        sys.exit(f"{len(errs)} spacing errors in the rores routing")
    x0, y0, x1, y1 = blk.bbox()
    if x0 < 0 or x1 > RES_W or y1 > RES_H or y0 < RES_PORT_Y:
        sys.exit(f"rores drawing {blk.bbox()} leaves the frame 0..{RES_W} x {RES_PORT_Y}..{RES_H}")
    for stem in (RES_NAME, RCELL):
        for ext in (".mag", ".ext", ".spice", ".gds"):
            (out / f"{stem}{ext}").unlink(missing_ok=True)
    for f in (f"{RES_NAME}_flat.gds", f"{RES_NAME}_full.gds"):
        (out / f).unlink(missing_ok=True)
    run_magic(rcell_tcl(), out, f"{RCELL}_build.log")
    run_magic(blk.magic_tcl() + f"flatten {RES_NAME}_flat\nload {RES_NAME}_flat\ncif ostyle lambda=0.30(ETRI)\n"
              f"gds write {RES_NAME}_flat.gds\n", out, f"{RES_NAME}_build.log")
    if not (out / f"{RES_NAME}_flat.gds").exists():
        sys.exit(f"Magic did not write {RES_NAME}_flat.gds (see {out / (RES_NAME + '_build.log')})")
    add_resistors(out / f"{RES_NAME}_flat.gds", out / f"{RES_NAME}_full.gds", info)
    bad = check_resistors(out / f"{RES_NAME}_full.gds", info)
    (out / f"{RES_NAME}_pins.json").write_text(json.dumps(res_pins_json(blk, info), indent=1))
    sq = sorted({r["squares"] for r in info["res"].values() if "squares" in r})
    print(f"{RES_NAME}: {(x1 - x0) * LAMBDA_UM:.2f} x {(y1 - y0) * LAMBDA_UM:.2f} um, {len(blk.rects)} rectangles, "
          f"{sum(1 for c in blk.cells if c[0] != RCELL)} standard cells, {len(info['res'])} resistors "
          f"({', '.join(f'{v:g}' for v in sq)} squares), {len(blk.ports)} ports; row ends at {info['end']}, "
          f"tracks {sorted({t for t in info['tracks'].values() if t is not None})}")
    for b in bad:
        print(f"  resistor check: {b}")
    if args.check:
        n, why = flat_drc(out, RES_NAME)
        print(f"  Magic DRC, flattened: {n}" + "".join(f"\n    {w}" for w in why))
        ok, line = etri_check(RES_NAME, str(out / "sch" / f"{RES_NAME}.spice"), out)
        print("  " + line + "   (hierarchical Magic DRC counts the kit cells' abutting rails; "
              "its GDS has no resistor layers)")
        # Netgen sees each resistor as the black box p2r40; extract the final GDS with the POLY2 resistors too
        sys.path.insert(0, str(REPO / "designs/etri050/ro"))
        import rores_lvs
        dev_ok, dev_line, dev_probs = rores_lvs.lvs(out / f"{RES_NAME}_full.gds")
        print("  " + dev_line + "".join(f"\n    {p}" for p in dev_probs[:20]))
        return 0 if (ok or "LVS MATCH" in line) and n == 0 and not bad and dev_ok else 1
    return 1 if bad else 0


def make_robank(args) -> int:
    out = args.out
    (out / "sch").mkdir(parents=True, exist_ok=True)
    (out / "sch" / f"{NAME}.spice").write_text(netlist())
    if args.netlist_only:
        return 0
    blk, info = build()
    errs = cb.spacing_errors(blk)
    for m, a, b in errs[:30]:
        print(f"  spacing {m}: {a} -- {b}")
    if errs:
        sys.exit(f"{len(errs)} spacing errors in the added routing")
    x0, y0, x1, y1 = blk.bbox()
    if x0 < 0 or x1 > W or y1 > H or y0 < PORT_Y:
        sys.exit(f"drawing {blk.bbox()} leaves the frame 0..{W} x {PORT_Y}..{H}")
    for ext in (".mag", ".ext", ".spice", ".gds"):
        (out / f"{NAME}{ext}").unlink(missing_ok=True)
    (out / f"{NAME}_flat.gds").unlink(missing_ok=True)
    run_magic(blk.magic_tcl() + f"flatten {NAME}_flat\nload {NAME}_flat\ncif ostyle lambda=0.30(ETRI)\n"
              f"gds write {NAME}_flat.gds\n", out, f"{NAME}_build.log")
    if not (out / f"{NAME}_flat.gds").exists():
        sys.exit(f"Magic did not write {NAME}_flat.gds (see {out / (NAME + '_build.log')})")
    (out / f"{NAME}_pins.json").write_text(json.dumps(pins_json(blk), indent=1))
    print(f"{NAME}: {(x1 - x0) * LAMBDA_UM:.1f} x {(y1 - y0) * LAMBDA_UM:.1f} um, {len(blk.rects)} rectangles, "
          f"{len(blk.cells)} standard cells, {len(blk.ports)} ports; row ends {info['ends']}")
    if args.check:
        n, why = flat_drc(out)
        print(f"  Magic DRC, flattened: {n}" + "".join(f"\n    {w}" for w in why))
        ok, line = etri_check(NAME, str(out / "sch" / f"{NAME}.spice"), out)
        print("  " + line + "   (hierarchical Magic DRC counts the kit cells' abutting rails)")
        return 0 if (ok or "LVS MATCH" in line) and n == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
