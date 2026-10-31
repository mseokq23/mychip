#!/usr/bin/env python3
"""Integrated TEG test chip for the ETRI 0.5 um MPW, generated from code and drawn by Magic.

Three blocks go into the kit's 28-pin bare pad frame (1.9 x 1.9 mm, MPW_PAD_28pin.gds):
  NMOS matrix   8 transistors, shared gate, source and substrate, one drain pad each
  PMOS matrix   6 transistors, shared gate, source and N-well, one drain pad each
  MOS capacitor NMOS 90 x 90 um with source, drain and body on the substrate (C-V)
21 pads are used; 7 stay free for the next version (PNP, Kelvin resistor, spare).

  python3 designs/etri050/gen/etri050_teg_chip.py              # build, check, write the chip GDS
  python3 designs/etri050/gen/etri050_teg_chip.py --no-check   # build only

Checks: Magic DRC of every block and of the core, KLayout DRC (kit deck) of the core and of
the whole chip, LVS of the flattened core against a generated netlist (pads as ports), and a
pad check (each used pad touches only its own net, free pads touch nothing).

Outputs in designs/etri050/teg/build/chip/:
  teg_chip_v0.gds          pad frame (unchanged) + core -> the chip
  teg_core_v0.gds/.mag     blocks + routing, as drawn by Magic
  teg_chip_v0_pins.md      pad map (pad number, side, net, what it connects to)
  sch/teg_core_v0.spice    netlist used for LVS

Routing: every chip-level route is metal3 and the routes are nested so that none cross.
Drain routes are 12 um wide, shared sources 30 um, substrate and N-well 20 um, gates 4.2 um
(series resistance; the pad map lists each route's length in squares for de-embedding). Block exits change layer with separate via1/via2 (the
process does not allow VIA2 stacked on VIA1).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etri050_mos import KINDS, LAMBDA_UM, REPO, Mos, etri_check, run_magic, um  # noqa: E402

CONFIG = REPO / "designs/etri050/teg/teg_chip_v0.json"
OUT = REPO / "designs/etri050/teg/build/chip"
FRAME = "pads_ETRI/GDS/MPW_PAD_28pin.gds"          # inside the design kit
CHIP, CORE = "teg_chip_v0", "teg_core_v0"

# Pad frame (um, from MPW_PAD_28pin.gds): 85 um pads, 7 per side, pitch 135 um.
PAD, PAD_PITCH, PAD_FIRST, PAD_IN, PAD_OUT = 85.0, 135.0, 502.5, 97.5, 1717.5


def lam(v_um: float) -> int:
    return round(v_um / LAMBDA_UM)


def pad_table():
    """{name: (number, side, (x0, y0, x1, y1) in um)}; numbered counter-clockwise from the top left."""
    pads, n = {}, 1
    sides = [("L", lambda k: (PAD_IN, PAD_FIRST + PAD_PITCH * (6 - k))),     # top -> bottom
             ("B", lambda k: (PAD_FIRST + PAD_PITCH * k, PAD_IN)),           # left -> right
             ("R", lambda k: (PAD_OUT, PAD_FIRST + PAD_PITCH * k)),          # bottom -> top
             ("T", lambda k: (PAD_FIRST + PAD_PITCH * (6 - k), PAD_OUT))]    # right -> left
    for side, ll in sides:
        for k in range(7):
            x, y = ll(k)
            pads[f"{side}{k + 1}"] = (n, side, (x, y, x + PAD, y + PAD))
            n += 1
    return pads


PADS = pad_table()


def pad_center(name):
    x0, y0, x1, y1 = PADS[name][2]
    return lam((x0 + x1) / 2), lam((y0 + y1) / 2)


# --------------------------------------------------------------------------- blocks
METAL_PLANES = {
    "metal1": ("m1",), "metal2": ("m2",), "metal3": ("m3",),
    "m2contact": ("m1", "m2"), "m3contact": ("m2", "m3"),
    "ndcontact": ("m1",), "pdcontact": ("m1",), "polycontact": ("m1",),
    "psubstratepcontact": ("m1",), "nsubstratencontact": ("m1",),
}
MIN_SPACE = {"m1": 3, "m2": 4, "m3": 4}     # lambda; official 0.8 / 1.0 / 1.0 um
CW = 6          # contact tile
PITCH = 150     # device pitch in a matrix (45 um): room for 12 um drain routes
EXT = 40        # bus extension on the exit side, for the exit vias
VIA = 14        # via tiles: 14 lambda = 4.2 um = 2 x 2 cuts


@dataclass
class Exit:
    x: int
    y: int
    side: str           # direction the route leaves the block: up, down, left, right


@dataclass
class Block:
    name: str
    shapes: list = field(default_factory=list)   # (net, magic_layer, x0, y0, x1, y1)
    exits: dict = field(default_factory=dict)    # net -> Exit
    ring: tuple = (0, 0, 0, 0)                   # outer boundary of the guard ring

    def add(self, net, layer, x0, y0, x1, y1):
        self.shapes.append((net, layer, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))

    def bbox(self):
        return (min(s[2] for s in self.shapes), min(s[3] for s in self.shapes),
                max(s[4] for s in self.shapes), max(s[5] for s in self.shapes))

    def mirrored(self):
        """Mirror about the x axis (y -> -y)."""
        flip = {"up": "down", "down": "up"}
        b = Block(self.name)
        b.shapes = [(n, l, x0, -y1, x1, -y0) for n, l, x0, y0, x1, y1 in self.shapes]
        b.exits = {k: Exit(e.x, -e.y, flip.get(e.side, e.side)) for k, e in self.exits.items()}
        x0, y0, x1, y1 = self.ring
        b.ring = (x0, -y1, x1, -y0)
        return b

    def placed(self, dx, dy, rename):
        """Shapes and exits moved by (dx, dy), block nets renamed to chip nets."""
        shapes = [(rename.get(n, n), l, x0 + dx, y0 + dy, x1 + dx, y1 + dy)
                  for n, l, x0, y0, x1, y1 in self.shapes]
        exits = {rename.get(k, k): Exit(e.x + dx, e.y + dy, e.side) for k, e in self.exits.items()}
        x0, y0, x1, y1 = self.ring
        return shapes, exits, (x0 + dx, y0 + dy, x1 + dx, y1 + dy)

    def magic_tcl(self):
        lines = [f"load {self.name}"]
        for _, layer, x0, y0, x1, y1 in self.shapes:
            lines += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"paint {layer}"]
        lines.append(f"save {self.name}")
        return "\n".join(lines) + "\n"


TAP_DIFF = {"nmos": "psubstratepdiff", "pmos": "nsubstratendiff"}


def add_ring(b, kind, x_in0, y_in0, x_in1, y_in1, net="B"):
    """Guard ring: diffusion ring + metal1 ring + one contact strip per side.

    Magic wants every contact area rectangular, so the four strips stop 2 lambda short of
    the corners; the diffusion and metal1 rings join them.
    """
    sides = [(x_in0 - CW, y_in0 - CW, x_in1 + CW, y_in0), (x_in0 - CW, y_in1, x_in1 + CW, y_in1 + CW),
             (x_in0 - CW, y_in0, x_in0, y_in1), (x_in1, y_in0, x_in1 + CW, y_in1)]
    for layer in (TAP_DIFF[kind], "metal1"):
        for r in sides:
            b.add(net, layer, *r)
    tap = KINDS[kind]["tap"]
    b.add(net, tap, x_in0 + 2, y_in0 - CW, x_in1 - 2, y_in0)          # bottom strip
    b.add(net, tap, x_in0 + 2, y_in1, x_in1 - 2, y_in1 + CW)          # top strip
    b.add(net, tap, x_in0 - CW, y_in0 + 2, x_in0, y_in1 - 2)          # left strip
    b.add(net, tap, x_in1, y_in0 + 2, x_in1 + CW, y_in1 - 2)          # right strip
    if KINDS[kind]["well"]:     # N-well 3 lambda beyond the n+ ring (>= 0.5 um)
        b.add(None, KINDS[kind]["well"], x_in0 - CW - 3, y_in0 - CW - 3, x_in1 + CW + 3, y_in1 + CW + 3)
    b.ring = (x_in0 - CW, y_in0 - CW, x_in1 + CW, y_in1 + CW)


def ring_exit_down(b, x_r, y_ring_out, net="B"):
    """Ring -> metal1 tab -> via1 -> metal2 -> via2 -> metal3 exit, going down."""
    y = y_ring_out
    b.add(net, "metal1", x_r, y - 2, x_r + VIA, y)
    b.add(net, "m2contact", x_r, y - 2 - VIA, x_r + VIA, y - 2)
    b.add(net, "metal2", x_r, y - 2 - VIA - 6, x_r + VIA, y - 2 - VIA)
    b.add(net, "m3contact", x_r, y - 2 - 2 * VIA - 6, x_r + VIA, y - 2 - VIA - 6)
    b.exits[net] = Exit(x_r + VIA // 2, y - 2 - 2 * VIA - 6, "down")


def matrix_block(name, kind, devs, exit_side):
    """Transistor row in a guard ring (drawn with the drain exits on top).

    bottom -> top: ring, source bus (metal1, 12 um), transistors, drain vias, gate bus, ring,
    drain exits. Gate and source leave at the exit_side end, the ring exit points down.
    """
    b = Block(name)
    xs = [i * PITCH for i in range(len(devs))]
    wmax = max(d.w for d in devs)
    sy1, sy0 = -4, -44                  # source bus (1.2 um clear of the drain contacts)
    gy0 = wmax + 12                     # gate bus, 3+ lambda above every drain via
    via_tops = []
    for i, (d, x) in enumerate(zip(devs, xs)):
        dn = f"D{i + 1}"
        for layer, x0, y0, x1, y1, term in d.device_rects():
            net = {"D": dn, "G": "G", "S": "S"}.get(term)
            b.add(net, layer, x + x0, y0, x + x1, y1)
        px0, py0, px1, py1 = d.gate_contact
        b.add("S", "metal1", x, sy1, x + CW, 0)                       # source stub
        b.add("G", "metal1", x + px0, py1, x + px1, gy0)              # gate stub
        vx0 = x + d.xact - 3                                          # drain via, right of the gate contact
        b.add(dn, "metal1", vx0, d.w, x + d.xact, d.w + 1)
        b.add(dn, "m2contact", vx0, d.w + 1, vx0 + VIA, d.w + 8)
        via_tops.append((dn, vx0, d.w + 8))
    g_x0 = min(x + d.gate_contact[0] for d, x in zip(devs, xs))
    g_x1 = max(x + d.gate_contact[2] for d, x in zip(devs, xs))
    d_x1 = max(x + d.xact + 11 for d, x in zip(devs, xs))             # right edge of the drain vias
    if exit_side == "left":
        bus_x0 = xs[0] - EXT
        b.add("G", "metal1", bus_x0, gy0, g_x1, gy0 + 6)
        b.add("S", "metal1", bus_x0, sy0, xs[-1] + CW, sy1)
        b.add("G", "m2contact", bus_x0, gy0, bus_x0 + 7, gy0 + 7)
        b.add("S", "m2contact", bus_x0, sy0 + 2, bus_x0 + VIA, sy1 - 2)
        x_in0, x_in1 = bus_x0 - 6, max(d_x1, g_x1) + 8
    else:
        bus_x1 = d_x1 + EXT
        b.add("G", "metal1", g_x0, gy0, bus_x1, gy0 + 6)
        b.add("S", "metal1", xs[0], sy0, bus_x1, sy1)
        b.add("G", "m2contact", bus_x1 - 7, gy0, bus_x1, gy0 + 7)
        b.add("S", "m2contact", bus_x1 - VIA, sy0 + 2, bus_x1, sy1 - 2)
        x_in0, x_in1 = xs[0] - 8, bus_x1 + 6
    y_in0, y_in1 = sy0 - 6, gy0 + 12
    add_ring(b, kind, x_in0, y_in0, x_in1, y_in1)
    # drain exits: metal2 up across the gate bus and the ring, via2 just outside
    ye = y_in1 + CW + 4
    for dn, vx0, ytop in via_tops:
        b.add(dn, "metal2", vx0, ytop, vx0 + VIA, ye)
        b.add(dn, "m3contact", vx0, ye, vx0 + VIA, ye + VIA)
        b.exits[dn] = Exit(vx0 + VIA // 2, ye + VIA, "up")
    # gate and source exits on the exit side: metal2 from the bus via across the ring, via2 outside
    if exit_side == "left":
        xo0, xo1 = x_in0 - CW - 4 - VIA, x_in0 - CW - 4
        strip_x0, strip_x1, xe = xo0, bus_x0, xo0
    else:
        xo0, xo1 = x_in1 + CW + 4, x_in1 + CW + 4 + VIA
        strip_x0, strip_x1, xe = bus_x1, xo1, xo1
    b.add("G", "metal2", strip_x0, gy0, strip_x1, gy0 + 7)
    b.add("G", "m3contact", xo0, gy0 - 4, xo1, gy0 + 10)
    b.exits["G"] = Exit(xe, gy0 + 3, exit_side)
    b.add("S", "metal2", strip_x0, sy0 + 2, strip_x1, sy1 - 2)
    b.add("S", "m3contact", xo0, sy0 + 2, xo1, sy1 - 2)
    b.exits["S"] = Exit(xe, (sy0 + sy1) // 2, exit_side)
    # guard ring exit (down), set back from the exit-side corner
    x_r = x_in0 + 40 if exit_side == "left" else x_in1 - 40 - VIA
    ring_exit_down(b, x_r, y_in0 - CW)
    return b


def cap_block(name, dev):
    """MOS capacitor: source and drain strapped to its own p+ ring, gate exit on top."""
    b = Block(name)
    for layer, x0, y0, x1, y1, term in dev.device_rects():
        b.add({"G": "C", "D": "B", "S": "B"}.get(term), layer, x0, y0, x1, y1)
    px0, py0, px1, py1 = dev.gate_contact
    cx = (px0 + px1) // 2
    b.add("C", "metal1", cx - 7, py1, cx + 7, py1 + 2)
    b.add("C", "m2contact", cx - 7, py1 + 2, cx + 7, py1 + 2 + VIA)
    x_in0, x_in1, y_in0, y_in1 = -8, dev.xact + 8, -8, py1 + 2 + VIA + 4
    b.add("B", "metal1", x_in0, 0, 0, dev.w)                          # source -> ring
    b.add("B", "metal1", dev.xact, 0, x_in1, dev.w)                   # drain -> ring
    add_ring(b, "nmos", x_in0, y_in0, x_in1, y_in1)
    ye = y_in1 + CW + 4
    b.add("C", "metal2", cx - 7, py1 + 2 + VIA, cx + 7, ye)
    b.add("C", "m3contact", cx - 7, ye, cx + 7, ye + VIA)
    b.exits["C"] = Exit(cx, ye + VIA, "up")
    return b


# --------------------------------------------------------------------------- routing
W_D, W_G, W_PWR, W_SRC = 40, 14, 66, 100   # route widths (lambda): 12, 4.2, 19.8, 30 um
TRACK0, TRACK = 50, 66              # first fan-out track below/above the exits, track pitch
SPACE = 20                          # 6 um between chip-level routes


SQUARES = {}                        # net -> metal3 squares of its chip-level route (centre line / width)


def path(net, pts, w, start_ext=7):
    """Metal3 path through Manhattan points; joints squared off, start reaches 7 lambda into the via."""
    SQUARES[net] = SQUARES.get(net, 0) + sum(abs(x1 - x0) + abs(y1 - y0)
                                             for (x0, y0), (x1, y1) in zip(pts, pts[1:])) / w
    h, out = w // 2, []
    for i, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:])):
        e0 = start_ext if i == 0 else h
        if y0 == y1:
            s = 1 if x1 > x0 else -1
            out.append((net, "metal3", min(x0 - s * e0, x1 + s * h), y0 - h, max(x0 - s * e0, x1 + s * h), y0 + h))
        elif x0 == x1:
            s = 1 if y1 > y0 else -1
            out.append((net, "metal3", x0 - h, min(y0 - s * e0, y1 + s * h), x0 + h, max(y0 - s * e0, y1 + s * h)))
        else:
            raise ValueError(f"route {net}: segment {pts[i]} -> {pts[i + 1]} is not Manhattan")
    return out


def fanout(nets, side_y, toward, end_y, side_targets):
    """Nested fan-out from block exits (all at y = side_y) to pads on the bottom/top side.

    nets: [(net, x_exit, pad_or_side_target, width)] ; toward = -1 (down) or +1 (up).
    Outer nets take the tracks closest to the block, so no two routes cross.
    side_targets: {net: (column_x, pad_y, end_x)} for nets that end on a left/right pad.
    """
    left, right, straight, routes = [], [], [], []
    for net, x, target, w in nets:
        if net in side_targets:
            (left if side_targets[net][0] < x else right).append((net, x, None, w))
            continue
        px, _ = pad_center(target)
        if abs(px - x) <= 100:
            straight.append((net, x, px, w))
        else:
            (left if px < x else right).append((net, x, px, w))
    # outer nets first: side-pad nets (outermost exit first), then by pad position
    left.sort(key=lambda n: (n[2] is not None, n[1] if n[2] is None else n[2]))
    right.sort(key=lambda n: (n[2] is not None, -n[1] if n[2] is None else -n[2]))
    for group in (left, right):
        for k, (net, x, px, w) in enumerate(group):
            t = side_y + toward * (TRACK0 + k * TRACK)
            if px is None:
                col, py, ex = side_targets[net]
                pts = [(x, side_y), (x, t), (col, t), (col, py), (ex, py)]
            else:
                pts = [(x, side_y), (x, t), (px, t), (px, end_y)]
            routes += path(net, pts, w)
    for net, x, px, w in straight:
        routes += path(net, [(x, side_y), (x, end_y)], w)
    return routes


# --------------------------------------------------------------------------- chip
def build(cfg):
    SQUARES.clear()
    nm = [Mos("nmos", w, l) for w, l in cfg["nmos"]]
    pm = [Mos("pmos", w, l) for w, l in cfg["pmos"]]
    if len(nm) != 8 or len(pm) != 6:
        raise ValueError("the pad plan needs exactly 8 NMOS and 6 PMOS")
    cap = Mos("nmos", *cfg["moscap"])
    nblk = matrix_block("nmos_block_v0", "nmos", nm, "left").mirrored()    # drains exit down
    pblk = matrix_block("pmos_block_v0", "pmos", pm, "right")              # drains exit up
    cblk = cap_block("moscap_block_v0", cap).mirrored()

    xc = lam(950)                   # chip centre
    y_bot, y_top = lam(300), lam(1620)   # drain exits of the NMOS / PMOS rows
    end_lo, end_hi = lam(140), lam(1760)  # route ends inside the pads

    def offset(blk, nets, y_target):
        xs = [blk.exits[n].x for n in nets]
        return xc - round(sum(xs) / len(xs)), y_target - blk.exits[nets[0]].y

    nd = [f"D{i + 1}" for i in range(8)]
    pd = [f"D{i + 1}" for i in range(6)]
    ox, oy = offset(nblk, nd, y_bot)
    n_shapes, n_ex, n_ring = nblk.placed(ox, oy, {**{f"D{i + 1}": f"ND{i + 1}" for i in range(8)},
                                                  "G": "NG", "S": "NS", "B": "SUB"})
    cx0 = n_ring[2] + 40 - cblk.ring[0]
    cy0 = y_bot - cblk.exits["C"].y
    c_shapes, c_ex, c_ring = cblk.placed(cx0, cy0, {"C": "CAP", "B": "SUB"})
    px_, py_ = offset(pblk, pd, y_top)
    p_shapes, p_ex, p_ring = pblk.placed(px_, py_, {**{f"D{i + 1}": f"PD{i + 1}" for i in range(6)},
                                                    "G": "PG", "S": "PS", "B": "NW"})
    placements = [(nblk, ox, oy), (cblk, cx0, cy0), (pblk, px_, py_)]

    core = []                                                         # chip-level shapes
    # substrate: strap the capacitor ring to the NMOS ring (metal1, abutting both)
    ys0, ys1 = max(n_ring[1], c_ring[1]) + 10, min(n_ring[3], c_ring[3]) - 10
    core.append(("SUB", "metal1", n_ring[2], ys0, c_ring[0], min(ys0 + 30, ys1)))

    # pad plan (net -> pad); see teg_chip_v0_pins.md
    # The lowest-current NMOS drain (ND8, rightmost) and the capacitor gate take the two right-side
    # pads, so the high-current drains next to the source exit get short routes to the bottom pads.
    plan = {"NG": "L6", "NS": "L5", "SUB": "L4", "ND8": "R1", "CAP": "R2", "NW": "R5", "PS": "R6", "PG": "R7"}
    plan.update({f"ND{i + 1}": f"B{i + 1}" for i in range(7)})
    plan.update({f"PD{i + 1}": f"T{7 - i}" for i in range(6)})

    col_l = [lam(234), lam(259)]                   # left columns: NG, NS (inner -> outer)
    col_r = [lam(1672), lam(1647), lam(1652)]      # right columns: PG and ND8, PS, CAP
    x_lend, x_rend = lam(140), lam(1760)
    py = {p: pad_center(p)[1] for p in ("L4", "L5", "L6", "R1", "R2", "R5", "R6", "R7")}

    # bottom fan-out: NMOS drains + capacitor gate
    nets = [(f"ND{i + 1}", n_ex[f"ND{i + 1}"].x, plan[f"ND{i + 1}"], W_D) for i in range(8)]
    nets.append(("CAP", c_ex["CAP"].x, "R2", W_G))
    core += fanout(nets, y_bot, -1, end_lo,
                   {"ND8": (col_r[0], py["R1"], x_rend), "CAP": (col_r[2], py["R2"], x_rend)})
    # NMOS gate / source to the left pads, substrate from the top of the ring
    e = n_ex["NG"]
    core += path("NG", [(e.x, e.y), (col_l[0], e.y), (col_l[0], py["L6"]), (x_lend, py["L6"])], W_G)
    e = n_ex["NS"]
    core += path("NS", [(e.x, e.y), (col_l[1], e.y), (col_l[1], py["L5"]), (x_lend, py["L5"])], W_SRC)
    e = n_ex["SUB"]
    core += path("SUB", [(e.x, e.y), (e.x, py["L4"]), (x_lend, py["L4"])], W_PWR)
    # top fan-out: PMOS drains
    nets = [(f"PD{i + 1}", p_ex[f"PD{i + 1}"].x, plan[f"PD{i + 1}"], W_D) for i in range(6)]
    core += fanout(nets, y_top, +1, end_hi, {})
    # PMOS gate / source to the right pads, N-well from the bottom of the ring
    e = p_ex["PG"]
    core += path("PG", [(e.x, e.y), (col_r[0], e.y), (col_r[0], py["R7"]), (x_rend, py["R7"])], W_G)
    e = p_ex["PS"]
    core += path("PS", [(e.x, e.y), (col_r[1], e.y), (col_r[1], py["R6"]), (x_rend, py["R6"])], W_SRC)
    e = p_ex["NW"]
    core += path("NW", [(e.x, e.y), (e.x, py["R5"]), (x_rend, py["R5"])], W_PWR)

    shapes = n_shapes + c_shapes + p_shapes + core
    devices = ([(f"ND{i + 1}", "NG", "NS", "SUB", d) for i, d in enumerate(nm)]
               + [("SUB", "CAP", "SUB", "SUB", cap)]
               + [(f"PD{i + 1}", "PG", "PS", "NW", d) for i, d in enumerate(pm)])
    return dict(blocks=[nblk, cblk, pblk], placements=placements, core=core, shapes=shapes,
                plan=plan, devices=devices)


# --------------------------------------------------------------------------- checks on our own data
def spacing_errors(shapes):
    """Different nets closer than the metal spacing on the same metal plane (or touching = short)."""
    per_plane = {}
    for net, layer, x0, y0, x1, y1 in shapes:
        for plane in METAL_PLANES.get(layer, ()):
            per_plane.setdefault(plane, []).append((net, x0, y0, x1, y1))
    errs = []
    for plane, items in per_plane.items():
        sp = MIN_SPACE[plane]
        items.sort(key=lambda r: r[1])
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if b[1] - a[3] >= sp:
                    break
                if a[0] == b[0] or a[0] is None or b[0] is None:
                    continue
                gap = max(b[1] - a[3], a[1] - b[3], b[2] - a[4], a[2] - b[4])
                if gap < sp:
                    errs.append(f"{plane}: {a[0]} and {b[0]} are {gap * LAMBDA_UM:.2f} um apart "
                                f"near ({a[1] * LAMBDA_UM:.1f}, {a[2] * LAMBDA_UM:.1f}) um")
    return errs


def pad_errors(shapes, plan):
    """Each used pad overlaps only its own net's metal; free pads overlap no metal at all."""
    owner = {p: n for n, p in plan.items()}
    errs = []
    for name, (_, _, (x0, y0, x1, y1)) in PADS.items():
        bx = (lam(x0), lam(y0), lam(x1), lam(y1))
        nets = {s[0] for s in shapes if s[1] in METAL_PLANES and s[2] < bx[2] and s[4] > bx[0]
                and s[3] < bx[3] and s[5] > bx[1]}
        want = {owner[name]} if name in owner else set()
        if nets != want:
            errs.append(f"pad {name}: touches {sorted(nets) or 'nothing'}, expected {sorted(want) or 'nothing'}")
    return errs


# --------------------------------------------------------------------------- outputs
def core_tcl(chip):
    lines = [f"load {CORE}"]
    for blk, dx, dy in chip["placements"]:
        x0, y0, _, _ = blk.bbox()
        lines += [f"box {um(x0 + dx)} {um(y0 + dy)} {um(x0 + dx)} {um(y0 + dy)}", f"getcell {blk.name}"]
    for _, layer, x0, y0, x1, y1 in chip["core"]:
        lines += [f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}", f"paint {layer}"]
    for net, pad in sorted(chip["plan"].items(), key=lambda kv: PADS[kv[1]][0]):
        x, y = route_end(chip, net, pad)
        lines += [f"box {um(x - 5)} {um(y - 5)} {um(x + 5)} {um(y + 5)}", f"label {net}"]
    lines += [f"box {um(-10)} {um(-10)} {um(lam(1910))} {um(lam(1910))}", "port makeall", f"save {CORE}"]
    return "\n".join(lines) + "\n"


def route_end(chip, net, pad):
    """A point on the net's metal3 inside the pad, for the port label."""
    x0, y0, x1, y1 = (lam(v) for v in PADS[pad][2])
    for n, layer, a0, b0, a1, b1 in chip["core"]:
        if n == net and layer == "metal3" and a0 < x1 and a1 > x0 and b0 < y1 and b1 > y0:
            return (max(a0, x0) + min(a1, x1)) // 2, (max(b0, y0) + min(b1, y1)) // 2
    raise ValueError(f"{net} does not reach pad {pad}")


def flatten_tcl():
    return (f"load {CORE}\nselect top cell\nexpand\nflatten {CORE}_flat\nload {CORE}_flat\n"
            f"box {um(-10)} {um(-10)} {um(lam(1910))} {um(lam(1910))}\nport makeall\nsave {CORE}_flat\n")


def netlist(chip):
    ports = sorted(chip["plan"], key=lambda n: PADS[chip["plan"][n]][0])
    lines = [f"* {CORE}: TEG core, ports are the pad nets (see {CHIP}_pins.md)",
             f".subckt {CORE} " + " ".join(ports)]
    for i, (d, g, s, bnet, dev) in enumerate(chip["devices"]):
        model = KINDS[dev.kind]["model"]
        lines.append(f"M{i + 1} {d} {g} {s} {bnet} {model} W={dev.w_um:g}u L={dev.l_um:g}u")
    lines.append(".ends")
    return "\n".join(lines) + "\n"


def pin_map(chip):
    plan = chip["plan"]
    desc = {"NG": "NMOS gate (all 8)", "NS": "NMOS source (all 8)", "SUB": "p-substrate: NMOS body, capacitor body",
            "CAP": "MOS capacitor gate (90 x 90 um)", "NW": "PMOS body: N-well", "PG": "PMOS gate (all 6)",
            "PS": "PMOS source (all 6)"}
    for i, (d, _, _, _, dev) in enumerate(chip["devices"]):
        if d.startswith(("ND", "PD")):
            desc[d] = f"{dev.kind.upper()} drain, W/L = {dev.w_um:g}/{dev.l_um:g} um"
    owner = {p: n for n, p in plan.items()}
    rows = ["| Pad | Side | Net | Connects to | Route (metal3 squares) |", "|---:|:---:|---|---|---:|"]
    for name, (n, side, _) in sorted(PADS.items(), key=lambda kv: kv[1][0]):
        net = owner.get(name, "-")
        sq = f"{SQUARES[net]:.0f}" if net in SQUARES else ""
        rows.append(f"| {n} | {name} | {net} | {desc.get(net, 'free (next version: PNP, Kelvin resistor, spare)')} | {sq} |")
    return (f"# {CHIP} pad map\n\nPads are numbered counter-clockwise from the top of the left side "
            "(L1-L7 top to bottom, B1-B7 left to right, R1-R7 bottom to top, T1-T7 right to left). "
            "The package pin numbers follow ETRI's bonding diagram; check them before designing the board.\n\n"
            + "\n".join(rows) + "\n\n"
            "Route squares count the chip-level metal3 from the block edge to the pad (centre line / width). "
            "Multiply by the PDK's metal3 sheet resistance for the series resistance to de-embed; the "
            "shared NMOS source also runs up to ~28 squares of metal1 bus inside the block (the "
            "high-current transistors sit next to its exit).\n")


def merge_chip(frame_gds, core_gds, out_gds):
    """Chip GDS = ETRI pad frame as delivered + the core written by Magic."""
    try:
        import klayout.db as db
        ly = db.Layout()
        ly.read(str(frame_gds))
        frame = ly.top_cell()
        ly.read(str(core_gds))
        core = ly.cell(CORE)
        top = ly.create_cell(CHIP)
        top.insert(db.CellInstArray(frame.cell_index(), db.Trans()))
        top.insert(db.CellInstArray(core.cell_index(), db.Trans()))
        ly.write(str(out_gds))
    except ImportError:
        import gdstk
        lib = gdstk.read_gds(str(frame_gds))
        frame = lib.top_level()[0]
        for c in gdstk.read_gds(str(core_gds)).cells:
            lib.add(c)
        core = next(c for c in lib.cells if c.name == CORE)
        top = gdstk.Cell(CHIP)
        top.add(gdstk.Reference(frame), gdstk.Reference(core))
        lib.add(top)
        lib.write_gds(str(out_gds))


def bash(cmd, cwd, *args):
    res = subprocess.run(["bash", "-c", 'source "$0"; ' + cmd, str(REPO / "scripts/etri050-env.sh"), *args],
                         cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return res.returncode, res.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-check", action="store_true", help="build only (no DRC, LVS, chip GDS)")
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text())
    chip = build(cfg)
    errs = spacing_errors(chip["shapes"]) + pad_errors(chip["shapes"], chip["plan"])
    for e in errs:
        print("PLAN  " + e)
    if errs:
        print(f"{len(errs)} problem(s) in the generated geometry; nothing written")
        return 1

    out = args.out.resolve()
    (out / "sch").mkdir(parents=True, exist_ok=True)
    for blk in chip["blocks"]:
        (out / f"{blk.name}.mag").unlink(missing_ok=True)
        run_magic(blk.magic_tcl(), out, f"{blk.name}_build.log")
    for name in (CORE, CORE + "_flat"):
        (out / f"{name}.mag").unlink(missing_ok=True)
    run_magic(core_tcl(chip), out, f"{CORE}_build.log")
    run_magic(flatten_tcl(), out, f"{CORE}_flat_build.log")
    (out / "sch" / f"{CORE}.spice").write_text(netlist(chip))
    (out / f"{CHIP}_pins.md").write_text(pin_map(chip))
    print(f"built {CORE} in {out}: {len(chip['devices'])} devices, {len(chip['plan'])} pads used")
    if args.no_check:
        return 0

    ok_all = True
    for blk in chip["blocks"]:
        ok, line = etri_check(blk.name, None, out)
        ok_all &= ok
        print(("PASS  " if ok else "FAIL  ") + line)
    ok, line = etri_check(CORE + "_flat", None, out)
    ok_all &= ok
    print(("PASS  " if ok else "FAIL  ") + line)
    rc, txt = bash('etri-lvs "$1" "$2" "$3" | tail -n 1', out, CORE + "_flat", f"sch/{CORE}.spice", CORE)
    lvs_ok = "MATCH   (" in txt and "property" not in txt
    pins_ok = "Cell pin lists are equivalent" in (out / f"{CORE}_flat_lvs.out").read_text(errors="replace")
    ok_all &= lvs_ok and pins_ok
    print(("PASS  " if lvs_ok and pins_ok else "FAIL  ") + txt.strip().splitlines()[-1]
          + ("" if pins_ok else "   (pin lists differ)"))

    # chip GDS: core as written by Magic (hierarchical) + the kit's pad frame, unchanged
    bash('etri-gds "$1" >/dev/null 2>&1', out, CORE)
    frame = Path(os.environ.get("ETRI050_DK", REPO / ".pdk/ETRI050_DesignKit")) / FRAME
    merge_chip(frame, out / f"{CORE}.gds", out / f"{CHIP}.gds")
    rc, txt = bash('rm -f "$1"_drc.lyrdb; etri-drc-klayout "$1".gds "$1"_drc.lyrdb >/dev/null 2>&1; '
                   '_etri_lyrdb_count "$1"_drc.lyrdb', out, CHIP)
    n = txt.strip().splitlines()[-1] if txt.strip() else "?"
    ok_all &= n == "0"
    print(("PASS  " if n == "0" else "FAIL  ") + f"KLayout DRC of the whole chip ({CHIP}.gds): {n} marker(s)")
    print(f"pad map: {out / (CHIP + '_pins.md')}")
    print(f"view: klayout-etri {out / (CHIP + '.gds')}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
