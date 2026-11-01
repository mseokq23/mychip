#!/usr/bin/env python3
"""RO bank of pdkv (plan "4. RO 뱅크"): INV, NAND, NOR and wire ring oscillators from kit cells.

Every RO has 31 stages. Stage 0 is NAND2X1(A = stage 30, B = ro_en<i>): a stopped RO holds a known
state and starts in its fundamental mode (with a free start the NAND RO can lock into its third
harmonic, plan simulation). A tap INVX1 -> INVX4 on stage 0's output drives ro_in<i> of the control
block, which picks one RO (rosel) and divides it by 256 onto OUT.

  index 0  inv   stages 1-30 INVX1
  index 1  nand  stages 1-30 NAND2X1, B at VDD
  index 2  nor   stages 1-30 NOR2X1, B at VSS
  index 4  wire  stages 1-30 INVX1, and every stage's output (0-30) carries a metal1 serpentine
                 0.9 um wide, three 99.6 um legs (about 307 um) over field: the plan's 300 um MET1 load

The plan's FO4 RO (index 3) and poly2-resistor RO (index 5) are not in this block: with the wire RO's
metal the bank fills the place left for it (x 856-1210, y 823-1146 um on the die). FO4 alone needs four
more rows and fits nowhere on the chip; the plan drops it first when area is short ("게이트 용량은
CBCM이 직접 잼"). The resistor RO (one row and 30 poly2 resistors of 80 um) fits the free strip above
the heater's return line (x 932-1405, y 1160-1297 um) and goes there as a block of its own. Until then
their control-block ports stay as they are (ro_en3/5 unconnected outputs, ro_in3/5 tied to VSS).

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

usage: python3 designs/etri050/gen/etri050_ro.py [--check] [--netlist-only]
       -> designs/etri050/ro/build/robank.mag, robank_flat.gds, sch/robank.spice, robank_pins.json
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
STAGE_CELL = {"inv": "INVX1", "nand": "NAND2X1", "nor": "NOR2X1", "wire": "INVX1"}
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
    """Instances of RO i: [(inst, cell, {pin: net})], stage outputs r<i>_<s>."""
    n = lambda s: f"r{i}_{s % NST}"
    out = [(f"XS{i}_0", "NAND2X1", {"A": n(NST - 1), "B": f"en{i}", "Y": n(0)})]
    for s in range(1, NST):
        cell = STAGE_CELL[kind]
        pins = {"A": n(s - 1), "Y": n(s)}
        if kind == "nand":
            pins["B"] = "VDD"
        elif kind == "nor":
            pins["B"] = "VSS"
        out.append((f"XS{i}_{s}", cell, pins))
    out.append((f"XT{i}a", "INVX1", {"A": n(0), "Y": f"t{i}"}))
    out.append((f"XT{i}b", "INVX4", {"A": f"t{i}", "Y": f"in{i}"}))
    return out


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


# ==== outputs and checks =============================================================================
def pins_json(blk):
    um = lambda v: round(v * LAMBDA_UM, 3)
    pins = {name: {"layer": layer, "box": [um(x0), um(y0), um(x1), um(y1)]}
            for name, layer, x0, y0, x1, y1 in blk.ports}
    rails = {f"gnd{r}": [um(row_y(r) - 4), um(row_y(r) + 4)] for r in range(0, ROWS + 1, 2)}
    return {"cell": NAME, "unit": "um, block coordinates (origin: lower left)", "origin_die": list(ORIGIN_DIE),
            "size": [um(W), um(H)], "pins": pins, "gnd_rails": rails, "rail_x": [um(GND_X0), um(RAIL_X1)],
            "kinds": {str(i): k for i, k in KINDS.items()}}


def flat_drc(out: Path):
    """Magic DRC of a flattened copy (hierarchical checks count the kit cells' abutting rails)."""
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
