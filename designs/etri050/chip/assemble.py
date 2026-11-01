"""Assemble pdkv_Top: pad ring + control block + direct devices + routing (KLayout batch mode).

Every part is a GDS with ETRI layer numbers, merged as in the kit's generate_chip.sh step 4 (the pad
ring keeps its own die coordinates, 97.5-1802.5 um):

  pdkv_Pad      designs/etri050/chip/build/pdkv_Pad.gds       (run_pad_ring.sh, Magic style ETRI-G)
  teg_ctrl_F    designs/etri050/ctrl/macro/teg_ctrl.gds.gz    (qflow block, notch-filled, 0.01 um grid)
  lsplit, mosc  designs/etri050/direct/build/*.gds            (etri050_direct.py, Magic style ETRI)
  pnp10, heater designs/etri050/direct/build/*.gds            (run_pdk_cells.sh)
  karray        designs/etri050/array/build/karray.gds        (etri050_array.py, Magic style ETRI)

The routes drawn here follow the rule document v1.1, not only the kit deck: VIA1/VIA2 exactly
0.8 x 0.8 um and 0.8 um apart with 0.6 um of metal around, no via1 on a contact and no via2 on a
via1, metal1 >= 0.8, metal2 >= 1.0, metal3 >= 1.2 um wide, >= 1.0 um between different shapes (the
pad ports are reached straight on, away from the other port of each PANA). Power, heater and force
lines are 9 um wide, just under the 10 um wide-metal class. Every coordinate is on the 0.01 um grid.

Floorplan (die um; the core window inside the GPIO cells is 442-1458): control block at x 537-1141,
y 460-761 (the array, RO and CBCM come above it and to its right later); scan channel y 442-460
under it; VSS as a metal1 line along the south and east edges from PVSS (E5) to the control block
ground bar and PNP2, plus a separate branch from PVSS to PNP1 and the L-split substrate tap; MOS-C on
the east edge between CHI (E3) and CLO (E4); L-split under its source force pad (N4) with the force
and gate lines on tracks near the north edge and the sense lines just below the cell. The thermal
group of the plan (heater + PNP + reference device): PNP1 beside the L-split (37 um between the
L-split channel and the PNP1 emitter), the heater under both, its long edge 32 um from each, so a
heater power warms the L-split and PNP1 alike and PNP1 also sees the L-split's own heating; the
heater return goes on its own line into PVSS. PNP2 in the far (south-west) corner next to PE2 (S1),
about 1 mm from the heater. The unused ro_in inputs of the control block (for the RO bank that
comes later) are tied to its ground bar.

Chip boundary and seal ring (-rd seal=0 leaves both out): the MyChip MPW standard chip is 1.9 x 1.9
mm and the kit centres the pad ring on it (generate_chip.sh puts it at 97.5 um), so CHIPBOUNDARY
(rule document 2.1, layer 0) is the box 0-1900 um. The seal ring is a block of its own, pdkv_SEAL,
written to <out>/pdkv_seal.gds and drawn in the outer 30 um as the 4.21 figure gives it (SEAL_RING).

Outputs: <out>/pdkv_Top.gds and <out>/pdkv_nets.json (expected nets as probe points, and the block
placements) for chip_check.py.

usage: klayout -b -r designs/etri050/chip/assemble.py -rd repo=<repo root> [-rd out=<dir>]
       [-rd pad=<pdkv_Pad.gds>] [-rd direct=<dir with lsplit, mosc, pnp10, heater .gds>] [-rd seal=0]
"""
import json
import os
import re

import pya

REPO = globals().get('repo') or os.getcwd()
OUT = globals().get('out') or os.path.join(REPO, 'designs/etri050/chip/build')
DIRECT = globals().get('direct') or os.path.join(REPO, 'designs/etri050/direct/build')
SRC = {
    'pad': globals().get('pad') or os.path.join(REPO, 'designs/etri050/chip/build/pdkv_Pad.gds'),
    'ctrl': os.path.join(REPO, 'designs/etri050/ctrl/macro/teg_ctrl.gds.gz'),
    'lsplit': os.path.join(DIRECT, 'lsplit.gds'),
    'mosc': os.path.join(DIRECT, 'mosc.gds'),
    'pnp10': os.path.join(DIRECT, 'pnp10.gds'),
    'heater': os.path.join(DIRECT, 'heater.gds'),
    'seal': os.path.join(OUT, 'pdkv_seal.gds'),
    'karray': globals().get('array') or os.path.join(REPO, 'designs/etri050/array/build/karray.gds'),
}
ARRPINS = os.path.join(os.path.dirname(SRC['karray']), 'karray_pins.json')
SEAL = str(globals().get('seal', '1')) != '0'
PINFILE = os.path.join(REPO, 'designs/etri050/ctrl/macro/teg_ctrl_pins.txt')
PADFILE = os.path.join(os.path.dirname(SRC['pad']), 'pad_pins.json')

ly = pya.Layout()
ly.dbu = 0.001
top = ly.create_cell('pdkv_Top')
LAY = {k: ly.layer(n, 0) for k, n in (('m1', 32), ('v1', 33), ('m2', 34), ('v2', 35), ('m3', 36))}


def nm(v):
    """um -> database units, refusing anything off the 0.01 um design grid."""
    r = int(round(v * 1000))
    if r % 10:
        raise ValueError(f'{v} um is off the 0.01 um grid')
    return r


def snap(v):
    """Pin coordinates of the macro, rounded as scripts/snap_grid.py rounded its GDS."""
    r = int(round(v * 1000))
    return (r + 5 if r % 10 == 5 else r) / 1000.0


def snap_down(v):
    return int(round(v * 1000)) // 10 * 10 / 1000.0


# ---- chip boundary and seal ring -----------------------------------------------------------------
DIE = 1900.0                  # MyChip MPW standard chip 1.9 x 1.9 mm; pad ring at 97.5-1802.5
RING = 30.0                   # rule document 4.21: seal ring 30 um, at the chip boundary (scribe side)
# Rule document 4.21 figure, read with each layer's digitized-area tone from table 2.1 (MET and ACT
# drawn dark, CONT, VIA and PSD drawn clear): drawn intervals across the ring, um from its inner (die)
# edge. The kit deck's 21.SEAL checks take the first number of each row as a line width instead.
SEAL_RING = {
    11: [(0.0, 30.0)],                                 # ACT: no LOCOS across the ring
    15: [(0.0, 30.0)],                                 # PSD: P+ (PWELL below; no NSD, POLY, NWELL)
    31: [(4.1, 4.9), (9.1, 9.9), (14.1, 14.9)],        # CONT 4.1 | 0.8 | 4.2 | 0.8 | 4.2 | 0.8 | 15.1
    32: [(0.0, 18.0)],                                 # MET1, then 12 um without metal to the scribe lane
    33: [(6.5, 7.5), (11.5, 12.5)],                    # VIA1 6.5 | 1.0 | 4.0 | 1.0 | 17.5
    34: [(0.0, 18.0)],                                 # MET2 18 | 12
    35: [(4.0, 5.0), (9.0, 10.0), (14.0, 15.0)],       # VIA2 4.0 | 1.0 | 4.0 | 1.0 | 4.0 | 1.0 | 15.0
    36: [(0.0, 18.0)],                                 # MET3 18 | 12
}


def write_seal(path):
    """pdkv_SEAL: every band as four abutting boxes (square corners, no polygons with holes)."""
    sl = pya.Layout()
    sl.dbu = 0.001
    cell = sl.create_cell('pdkv_SEAL')
    for n, bands in SEAL_RING.items():
        shapes = cell.shapes(sl.layer(n, 0))
        for a, b in bands:
            o, i = nm(RING - b), nm(RING - a)              # distances from the chip edge
            d = nm(DIE)
            for box in (pya.Box(o, o, d - o, i), pya.Box(o, d - i, d - o, d - o),
                        pya.Box(o, i, i, d - i), pya.Box(d - i, i, d - o, d - i)):
                shapes.insert(box)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sl.write(path)


# ---- blocks --------------------------------------------------------------------------------------
cells, placed = {}, []


def block(key):
    if key not in cells:
        src = pya.Layout()
        src.read(SRC[key])
        if len(src.top_cells()) != 1:
            raise RuntimeError(f'{SRC[key]}: {len(src.top_cells())} top cells')
        cell = ly.create_cell(src.top_cell().name)
        cell.copy_tree(src.top_cell())
        cells[key] = cell
    return cells[key]


def place(key, x, y, rot=0, mirror=False, name=None):
    t = pya.Trans(rot // 90, mirror, nm(x), nm(y))
    top.insert(pya.CellInstArray(block(key).cell_index(), t))
    placed.append({'name': name or key, 'gds': SRC[key], 'x': x, 'y': y, 'rot': rot, 'mirror': mirror})
    return lambda cx, cy: (lambda p: (p.x / 1000.0, p.y / 1000.0))(t * pya.Point(nm(cx), nm(cy)))


pads = {}
for p in json.load(open(PADFILE))['pads']:
    pads[p['pad'] + ':' + p['pin']] = p['rect']
ctrl_pins = {}
for line in open(PINFILE):
    if line.startswith('#') or not line.strip():
        continue
    name, layer, *c = line.split()
    ctrl_pins[name] = (layer, *[snap(float(v)) for v in c])

CTRL = (546.30, 463.52)       # teg_ctrl_F bbox (-9.3,-3.52)-(594.6,297.58) -> die (537.0,460.0)-(1140.9,761.1)
LSP = (962.90, 1388.00)       # lsplit active lower left: source force (cell x 4.5) under N4
MOSC = (1219.60, 1005.90)     # mirrored: gate bar (CHI) at the bottom facing E3, CLO bar on top
PNP1 = (980.00, 1368.00)      # beside the L-split (cell x 959.0-974.6), emitter centre (1004.5, 1392.5)
PNP2 = (455.00, 458.00)       # far (south-west) corner, next to PE2 (S1)
HEAT = (1056.00, 1361.60)     # rotated 180: x 932-1056, y 1340-1361.6 under the L-split and PNP1;
                              # head A (cell left) on the east end toward HT (E7)

place('pad', 0, 0, name='pdkv_Pad')
if SEAL:
    write_seal(SRC['seal'])
    place('seal', 0, 0, name='pdkv_SEAL')
    top.shapes(ly.layer(0, 0)).insert(pya.Box(0, 0, nm(DIE), nm(DIE)))     # CHIPBOUNDARY
place('ctrl', *CTRL, name='teg_ctrl')
place('lsplit', *LSP)
mosc_at = place('mosc', *MOSC, mirror=True)
place('pnp10', *PNP1, name='pnp1')
place('pnp10', *PNP2, name='pnp2')
heat_at = place('heater', *HEAT, rot=180)


def pin_die(name):
    _, x1, y1, x2, y2 = ctrl_pins[name]
    return x1 + CTRL[0], y1 + CTRL[1], x2 + CTRL[0], y2 + CTRL[1]


# ---- drawing helpers (um) ------------------------------------------------------------------------
def rect(layer, x1, y1, x2, y2):
    top.shapes(LAY[layer]).insert(pya.Box(nm(min(x1, x2)), nm(min(y1, y2)), nm(max(x1, x2)), nm(max(y1, y2))))


def vias(kind, x1, y1, x2, y2):
    """Both metals over the rectangle and as many 0.8 um cuts as fit (0.8 um apart, 0.6 um inside)."""
    cut, lo, hi = ('v1', 'm1', 'm2') if kind == 1 else ('v2', 'm2', 'm3')
    rect(lo, x1, y1, x2, y2)
    rect(hi, x1, y1, x2, y2)
    n = [int(round((b - a) - 2.0, 3) // 1.6) + 1 for a, b in ((x1, x2), (y1, y2))]
    if min(n) < 1:
        raise ValueError(f'via{kind} rectangle {x1},{y1},{x2},{y2} is too small')
    x0 = snap_down((x1 + x2 - (n[0] - 1) * 1.6 - 0.8) / 2)
    y0 = snap_down((y1 + y2 - (n[1] - 1) * 1.6 - 0.8) / 2)
    for i in range(n[0]):
        for j in range(n[1]):
            cx, cy = round(x0 + i * 1.6, 2), round(y0 + j * 1.6, 2)
            rect(cut, cx, cy, cx + 0.8, cy + 0.8)
    return n[0] * n[1]


def via(kind, cx, cy):
    """One cut centred at (cx, cy) with 2.0 um pads on both metals."""
    return vias(kind, cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0)


nets = {}


def expect(net, what, layer, x, y):
    nets.setdefault(net, []).append({'at': what, 'layer': layer, 'x': round(x, 3), 'y': round(y, 3)})


def port_probe(net, key):
    x1, y1, x2, y2 = pads[key]
    expect(net, 'pad ' + key, 'm2', (x1 + x2) / 2, (y1 + y2) / 2)


# ---- VDD: PVDD (W1) -> control block vdd bar (metal1, x 537.0-546.0) -------------------------------
rect('m2', 440.60, 535.00, 528.00, 544.00)
vias(1, 519.00, 535.00, 528.00, 544.00)
rect('m1', 519.00, 535.00, 540.00, 544.00)
port_probe('VDD', 'W1:PVDD')
expect('VDD', 'ctrl vdd bar', 'm1', 541.50, 600.00)

# ---- VSS: PVSS (E5) -> metal1 line along the east and south edges --------------------------------
rect('m2', 1447.00, 1040.00, 1459.40, 1049.00)            # strap into the PVSS port (lower part)
vias(1, 1447.00, 1040.00, 1456.00, 1049.00)
rect('m1', 1447.00, 446.00, 1456.00, 1049.00)             # east edge
rect('m1', 455.00, 446.00, 1456.00, 455.00)               # south edge, under the scan channel
rect('m1', 1131.60, 450.00, 1140.60, 465.00)              # up into the control block gnd bar
port_probe('VSS', 'E5:PVSS')
expect('VSS', 'ctrl gnd bar', 'm1', 1136.10, 600.00)

# ---- control block: unused ro_in inputs tied to the gnd bar (top edge, until the RO bank exists) ----
rect('m1', 1131.60, 753.50, 1140.60, 767.00)              # gnd bar extended above the block
rect('m1', 1085.00, 765.00, 1140.60, 767.00)
for i in range(6):
    x1, y1, x2, y2 = pin_die(f'ro_in[{i}]')
    rect('m2', x1, y2 - 0.50, x2, 767.00)
    via(1, snap_down((x1 + x2) / 2), 766.00)
    expect('VSS', f'ctrl ro_in[{i}]', 'm2', (x1 + x2) / 2, y2 - 0.30)

# ---- scan pins: block bottom edge (y 460.0) -> south pads, four metal3 tracks in y 442-460 ---------
TRACK = {'out': 444.50, 'cck': 444.50, 'sle': 447.50, 'sdi': 450.50, 'sck': 453.50}
SCAN = {'out': 'S5:OUT', 'cck': 'S6:CCK', 'sle': 'S4:SLE', 'sdi': 'S2:SDI', 'sck': 'S3:SCK'}
for net, key in SCAN.items():
    x1, y1, x2, y2 = pin_die(net)
    ty = TRACK[net]
    cx = snap_down((x1 + x2) / 2)
    rect('m2', x1, ty, x2, y1 + 1.00)                      # down from the pin (its bottom is y1 = 460.0)
    via(2, cx, ty)
    px1, _, px2, py2 = pads[key]
    pcx = snap_down((px1 + px2) / 2)
    rect('m3', min(cx, pcx) - 1.00, ty - 0.60, max(cx, pcx) + 1.00, ty + 0.60)
    via(2, pcx, ty)
    rect('m2', pcx - 1.00, py2 - 1.00, pcx + 1.00, ty)     # down into the PIC Y / POB4 A port
    port_probe(net.upper(), key)
    expect(net.upper(), f'ctrl {net}', 'm2', (x1 + x2) / 2, y1 + 0.40)

# ---- PNPs: emitter through four via1 between its 3 x 3 contacts, base ring tied to collector ring --
for (px, py), pe, net in ((PNP1, 'E6:PE1', 'PE1'), (PNP2, 'S1:PE2', 'PE2')):
    for cx in (23.10, 25.90):
        for cy in (23.10, 25.90):
            rect('v1', px + cx - 0.40, py + cy - 0.40, px + cx + 0.40, py + cy + 0.40)
    rect('m2', px + 22.10, py + 22.10, px + 26.90, py + 26.90)
    rect('m1', px + 6.00, py + 23.50, px + 13.50, py + 25.50)
    port_probe(net, pe)
    expect(net, f'{net} emitter', 'm1', px + 24.50, py + 20.50)
    expect('VSS', f'{net} base ring', 'm1', px + 14.00, py + 30.00)
    expect('VSS', f'{net} collector ring', 'm1', px + 5.50, py + 40.00)
rect('m1', 475.00, 450.00, 484.00, 463.50)                 # PNP2 collector ring <- south VSS line
rect('m2', 477.10, 480.10, 521.45, 482.10)                 # PE2: east over the rings, then down to S1
rect('m2', 519.45, 441.00, 521.45, 482.10)

# ---- MOS-C: CHI (bottom bar after mirroring) -> E3 PADR, CLO (top bar) -> E4 PADR -------------------
rect('m1', 1372.00, 783.00, 1381.00, 794.40)               # gate bar (x 1270.45-1382.35) extended down
vias(1, 1372.00, 783.00, 1381.00, 791.00)
rect('m2', 1372.00, 783.00, 1459.40, 791.00)               # under the cell edge (y 792.6) to E3
rect('m1', 1435.20, 1011.90, 1445.00, 1019.70)             # CLO bar (x 1216.6-1436.2) extended past the cell
vias(1, 1437.00, 1011.90, 1445.00, 1019.70)
rect('m2', 1437.00, 921.45, 1445.00, 1019.70)
rect('m2', 1437.00, 921.45, 1459.40, 929.45)
port_probe('CHI', 'E3:CHI')
port_probe('CLO', 'E4:CLO')
expect('CHI', 'mosc gate bar', 'm1', *mosc_at(100.0, 212.4))
expect('CLO', 'mosc well/p+ bar', 'm1', *mosc_at(100.0, -6.9))

# ---- heater: head A (east end) -> HT (E7 PAD), head B (west end) -> PVSS (E5 upper part) alone -----
rect('m1', 1054.20, 1350.00, 1062.00, 1359.00)             # head A (x 1053.4-1055.2) extended east
vias(1, 1055.80, 1350.00, 1062.00, 1359.00)                # cuts >= 1.8 um from the head contacts
rect('m2', 1055.80, 1350.00, 1459.40, 1359.00)             # east into E7 PAD (y 1348.8-1396.0)
rect('m1', 926.00, 1350.00, 933.80, 1359.00)               # head B (x 932.8-934.6) extended west
vias(1, 926.00, 1350.00, 932.20, 1359.00)
rect('m2', 922.00, 1150.00, 931.00, 1359.00)               # its own return line: down, kept above
rect('m2', 922.00, 1150.00, 1425.00, 1159.00)              # the RO area (y < 1142), east, then
rect('m2', 1416.00, 1114.00, 1425.00, 1159.00)             # into PVSS (y 1037.6-1132.4)
rect('m2', 1416.00, 1114.00, 1459.40, 1123.00)
port_probe('HT', 'E7:HT')
expect('HT', 'heater head A', 'm1', *heat_at(1.70, 10.80))
expect('VSS', 'heater head B', 'm1', *heat_at(122.30, 10.80))

# ---- PNP1: emitter -> PE1 (E6 PADR); base + collector -> VSS branch from the middle of PVSS -------
rect('m2', 1003.50, 1298.00, 1005.50, 1394.90)             # down from the emitter pad, over the heater
rect('m2', 1003.50, 1298.00, 1408.00, 1300.00)
rect('m2', 1406.00, 1194.00, 1408.00, 1300.00)
rect('m2', 1406.00, 1194.00, 1459.40, 1196.00)             # into E6 PADR (y 1181.65-1209.25)
rect('m2', 1430.00, 1060.00, 1459.40, 1066.00)             # VSS branch: PVSS (middle) ...
vias(1, 1431.00, 1060.00, 1440.00, 1066.00)
rect('m1', 1434.00, 1060.00, 1438.00, 1385.00)             # ... up the east side ...
rect('m1', 1023.00, 1381.00, 1438.00, 1385.00)             # ... to the PNP1 collector ring (east side)

# ---- L-split: force + gate on tracks near the north edge, sense below the cell ---------------------
X0, Y0 = LSP
# gate: metal1 bar (x 959.9-961.7) -> west at the poly-contact level -> metal2 up -> metal3 west -> N1
rect('m1', 944.00, Y0 + 9.30, 961.70, Y0 + 11.30)
via(1, 945.00, Y0 + 10.30)
rect('m2', 944.40, Y0 + 10.30, 945.60, 1440.00)
via(2, 945.00, 1440.00)
rect('m3', 519.45, 1439.20, 946.00, 1440.80)
via(2, 520.45, 1440.00)
rect('m2', 519.45, 1440.00, 521.45, 1459.00)
# drain 1 force: stub (x 963.2-964.4) -> jog west -> 9 um metal2 up -> 9 um metal3 west -> N2 PAD
rect('m2', 947.00, Y0 + 17.40, 964.40, Y0 + 20.00)
rect('m2', 947.00, Y0 + 17.40, 956.00, 1429.00)
vias(2, 947.00, 1420.00, 956.00, 1429.00)
rect('m3', 692.90, 1420.00, 956.00, 1429.00)
vias(2, 692.90, 1420.00, 701.90, 1429.00)
rect('m2', 692.90, 1420.00, 701.90, 1459.00)
# source force: stub (x 966.8-968.0) -> straight up, 9 um once clear of the jog -> N4 PAD
rect('m2', 966.80, Y0 + 17.00, 968.00, Y0 + 21.20)
rect('m2', 959.00, Y0 + 21.20, 968.00, 1459.00)
# drain 2 force: stub (x 971.0-972.2) -> 9 um metal2 up -> 9 um metal3 east -> N6 PAD
rect('m2', 971.00, Y0 + 17.40, 980.00, 1429.00)
vias(2, 971.00, 1420.00, 980.00, 1429.00)
rect('m3', 971.00, 1420.00, 1241.90, 1429.00)
vias(2, 1232.90, 1420.00, 1241.90, 1429.00)
rect('m2', 1232.90, 1420.00, 1241.90, 1459.00)
# sense: stubs end at y Y0-9; D1 west and S east on one metal3 level, D2 east one level lower
for xs, ty, xp in ((963.80, 1378.00, 790.45), (967.40, 1378.00, 1060.45), (971.60, 1374.00, 1330.45)):
    rect('m2', xs - 0.60, ty, xs + 0.60, Y0 - 8.40)       # stub extended down to the via
    via(2, xs, ty)
    rect('m3', min(xs, xp) - 1.00, ty - 0.60, max(xs, xp) + 1.00, ty + 0.60)
    via(2, xp, ty)
    rect('m2', xp - 1.00, ty, xp + 1.00, 1459.00)
# substrate tap (metal1, y Y0-6.6..-4.8) -> east to the PNP1 collector ring next to it (VSS)
rect('m1', X0 + 10.80, Y0 - 6.60, PNP1[0] + 5.50, Y0 - 4.80)
for net, key in (('LG', 'N1:LG'), ('D1', 'N2:LD1F'), ('D1', 'N3:LD1S'), ('S', 'N4:LSF'), ('S', 'N5:LSS'),
                 ('D2', 'N6:LD2F'), ('D2', 'N7:LD2S')):
    port_probe(net, key)
for net, cx in (('D1', 0.90), ('S', 4.50), ('D2', 8.70)):
    expect(net, f'lsplit {net} contact strip', 'm1', X0 + cx, Y0 + 5.00)
expect('LG', 'lsplit gate metal', 'm1', X0 - 2.10, Y0 + 14.00)
expect('VSS', 'lsplit substrate tap', 'm1', X0 + 4.50, Y0 - 5.70)

# ---- Kelvin array (designs/etri050/gen/etri050_array.py) ----------------------------------------------
# Block origin = row 0 bottom, left edge of the leftmost column. West of the control block's column
# select pins and right of the west pads (ANW, ADF, ADS, ASF, ASS, AG); its bottom leaves a 64 um
# channel above the control block for the 40 select lines, its top (1376.0) stays under the AG line.
ARR = (458.00, 950.00)
arr_at = place('karray', *ARR, name='karray')
apins = json.load(open(ARRPINS))['pins']


def apin(name):
    x0, y0, x1, y1 = apins[name]['box']
    return round(ARR[0] + x0, 3), round(ARR[1] + y0, 3), round(ARR[0] + x1, 3), round(ARR[1] + y1, 3)


def pin_cx(name):
    x1, _, x2, _ = pin_die(name)
    return round((x1 + x2) / 2, 2)


ARR_X1 = apin('row_line0')[2]                      # right edge of the block (row driver side)
ARR_Y0 = apin('col_sel0')[1]                       # bottom edge (column select ports)
CTRL_TOP = pin_die('col_sel[0]')[3]                # top edge of the control block pins


def channel(nets, y0, pitch, ymax):
    """Track per net (metal3) in the channel above the control block; metal2 stubs down to the pins
    and up to the array. nets: [(name, x_bottom, x_top)]. A net whose bottom stub would run into
    another net's top stub (same x) must take the lower track (vertical constraint)."""
    pad, gap = 1.0, 1.0
    iv = {n: (min(xb, xt) - pad, max(xb, xt) + pad) for n, xb, xt in nets}
    below = {n: set() for n, _, _ in nets}
    for a, xba, _ in nets:
        for b, _, xtb in nets:
            if a != b and abs(xba - xtb) < 2 * pad + 0.6 + gap:
                below[b].add(a)                    # a's track below b's
    left, tracks = {n for n, _, _ in nets}, {}
    t = 0
    while left:
        last, placed = None, []
        for n in sorted(left, key=lambda n: iv[n][0]):
            if below[n] & left:
                continue
            if last is None or iv[n][0] >= last + gap:
                placed.append(n)
                last = iv[n][1]
        if not placed:
            raise RuntimeError('channel: cyclic vertical constraints')
        for n in placed:
            tracks[n] = round(y0 + t * pitch, 2)
        left -= set(placed)
        t += 1
    if max(tracks.values()) + pad + gap > ymax:
        raise RuntimeError(f'channel: {t} tracks do not fit under y {ymax}')
    return tracks, t


# select nets: column switches (ports at the array bottom) and row drivers (a bus of metal2 lines right of
# the array, one per net, in the order of the control block pins so that the channel stays narrow)
def ctrl_name(n):
    """row_selb3 -> row_selb[3] (control block pin name)."""
    m = re.fullmatch(r'(col_selb|col_sel|row_selb|row_sel)(\d+)', n)
    return f'{m.group(1)}[{m.group(2)}]'


row_nets = sorted([f'row_sel{r}' for r in range(12)] + [f'row_selb{r}' for r in range(12)],
                  key=lambda n: pin_cx(ctrl_name(n)))
BUS_X0, BUS_PITCH = round(ARR_X1 + 3.20, 2), 3.00
bus_x = {n: round(BUS_X0 + i * BUS_PITCH, 2) for i, n in enumerate(row_nets)}


nets_ch = []
for c in range(8):
    for k in ('col_sel', 'col_selb'):
        x0, _, x1, _ = apin(f'{k}{c}')
        nets_ch.append((f'{k}{c}', pin_cx(ctrl_name(f'{k}{c}')), round((x0 + x1) / 2, 2)))
for n in row_nets:
    nets_ch.append((n, pin_cx(ctrl_name(n)), bus_x[n]))
tracks, n_tracks = channel(nets_ch, round(CTRL_TOP + 2.55, 2), 3.00, ARR_Y0)
row_y = {r: apin(f'row_line{r}')[1] - 3.00 for r in range(12)}       # row bottom (sel line at +3.0)
for n, xb, xt in nets_ch:
    ty = tracks[n]
    _, pby0, _, _ = pin_die(ctrl_name(n))
    rect('m2', xb - 0.60, pby0, xb + 0.60, ty + 1.00)                   # up from the control block pin
    if abs(xb - xt) < 1.60:      # two cuts would be closer than 0.8 um (VIA2.S1): one cut, pads over both
        vias(2, min(xb, xt) - 1.00, ty - 1.00, max(xb, xt) + 1.00, ty + 1.00)
    else:
        via(2, xb, ty)
        rect('m3', min(xb, xt) - 1.00, ty - 0.60, max(xb, xt) + 1.00, ty + 0.60)
        via(2, xt, ty)
    if n.startswith('col'):
        rect('m2', xt - 0.60, ty - 1.00, xt + 0.60, ARR_Y0 + 1.20)       # up into the column switch line
        expect(n.upper(), 'array port', 'm2', xt, ARR_Y0 + 0.60)
    else:
        r = int(re.search(r'\d+$', n).group())
        yl = row_y[r] + (5.40 if n.startswith('row_selb') else 3.00)
        rect('m2', xt - 0.60, ty - 1.00, xt + 0.60, yl + 1.60)           # bus line up to its row
        via(1, xt, round(yl + 0.60, 2))
        rect('m1', ARR_X1 - 0.60, yl, xt + 1.00, yl + 1.20)              # row line extended to the bus
        expect(n.upper(), 'array row line', 'm1', ARR_X1 - 0.30, yl + 0.60)
    expect(n.upper(), 'ctrl pin', 'm2', xb, pby0 + 0.40)
    expect(n.upper(), 'channel track', 'm3', (xb + xt) / 2, ty)

# AG: W7 PADR -> metal3 above the array -> down to the AG bus at the driver column
xp1, yp0, xp2, yp1 = pads['W7:AG']
ag_y = round((yp0 + yp1) / 2, 2)
ax0, _, ax1, ay1 = apin('AG')
ag_x = round((ax0 + ax1) / 2, 2)
rect('m2', xp1, ag_y - 1.00, xp2 + 2.00, ag_y + 1.00)
via(2, xp2 + 1.00, ag_y)
rect('m3', xp2, ag_y - 0.60, ag_x + 1.00, ag_y + 0.60)
via(2, ag_x, ag_y)
rect('m2', ag_x - 0.60, ay1 - 1.20, ag_x + 0.60, ag_y)
port_probe('AG', 'W7:AG')
expect('AG', 'array AG bus', 'm2', ag_x, ay1 - 0.60)

# left channel (x 442-446): pad ports turn to metal3 at once; ANW runs up in metal2 at x 445.4-446.6
X_ANW_V = (445.40, 446.60)


def pad_to_m3(key, y_lo, y_hi):
    """Metal2 stub out of a west pad port and via2 cuts onto metal3, y_lo..y_hi (>= 2 um)."""
    xp1, _, xp2, _ = pads[key]
    rect('m2', xp1, y_lo, xp2 + 2.00, y_hi)
    vias(2, xp2, y_lo, xp2 + 2.00, y_hi)


# ANW: W2 PADR -> metal2 up the left channel -> metal3 over the VDD strap -> ANW strap of the PMOS rows
xp1, yp0, xp2, yp1 = pads['W2:ANW']
anw_y = round((yp0 + yp1) / 2, 2)
nx0, ny0, nx1, _ = apin('ANW_BOT')
anw_j = round(ny0 + 3.00, 2)
rect('m2', xp1, anw_y - 1.00, X_ANW_V[1], anw_y + 1.00)
rect('m2', X_ANW_V[0], anw_y - 1.00, X_ANW_V[1], anw_j + 1.00)
via(2, round((X_ANW_V[0] + X_ANW_V[1]) / 2, 2), anw_j)
rect('m3', X_ANW_V[0] - 0.40, anw_j - 0.60, (nx0 + nx1) / 2 + 1.00, anw_j + 0.60)
via(2, round((nx0 + nx1) / 2, 2), anw_j)
port_probe('ANW', 'W2:ANW')
expect('ANW', 'array ANW strap', 'm2', (nx0 + nx1) / 2, ny0 + 10.00)

# ADF: W3 PAD -> 9 um metal3 up to the array's ADF bus (left end)
fx0, fy0, fx1, fy1 = apin('ADF')
xp1, yp0, xp2, yp1 = pads['W3:ADF']
pad_to_m3('W3:ADF', yp1 - 12.00, yp1 - 3.00)
rect('m3', xp2, yp1 - 12.00, fx0 + 5.00, yp1 - 3.00)
rect('m3', fx0 - 4.00, yp1 - 12.00, fx0 + 5.00, fy1)
port_probe('ADF', 'W3:ADF')
expect('ADF', 'array ADF bus', 'm3', fx0 + 2.00, (fy0 + fy1) / 2)

# ADS: W4 PADR -> metal3 down the left channel -> the array's ADS landing (metal3)
sx0, sy0, sx1, sy1 = apin('ADS_M3')
xp1, yp0, xp2, yp1 = pads['W4:ADS']
ads_y = round((yp0 + yp1) / 2, 2)
pad_to_m3('W4:ADS', ads_y - 1.00, ads_y + 1.00)
rect('m3', xp2, sy0, xp2 + 1.20, ads_y + 1.00)
rect('m3', xp2, sy0, sx1, sy1)
port_probe('ADS', 'W4:ADS')
expect('ADS', 'array ADS line', 'm1', apin('ADS')[0] + 0.60, apin('ADS')[1] + 0.60)

# ASF: W5 PAD -> 9 um metal3 straight into the source plate's left edge
ex0, ey0, ex1, ey1 = apin('SRC_EDGE')
xp1, yp0, xp2, yp1 = pads['W5:ASF']
asf_y = round((yp0 + yp1) / 2, 2)
pad_to_m3('W5:ASF', asf_y - 4.50, asf_y + 4.50)
rect('m3', xp2, asf_y - 4.50, ex1, asf_y + 4.50)
port_probe('SRC', 'W5:ASF')
expect('SRC', 'array source plate', 'm3', ex0 + 20.00, ey0 + 60.00)

# ASS: W6 PADR -> metal3 down the left channel -> the plate's sense line (slot to the plate centre)
tx0, ty0, tx1, ty1 = apin('ASS')
xp1, yp0, xp2, yp1 = pads['W6:ASS']
ass_y = round((yp0 + yp1) / 2, 2)
pad_to_m3('W6:ASS', ass_y - 1.00, ass_y + 1.00)
rect('m3', xp2, ty0, xp2 + 1.20, ass_y + 1.00)
rect('m3', xp2, ty0, tx1, ty1)
port_probe('SRC', 'W6:ASS')

# VDD and VSS of the array: straps extended down to the W1 VDD line and the south VSS line
vx0, vy0, vx1, _ = apin('VDD')
rect('m2', vx0, 535.00, vx1, vy0 + 1.20)
expect('VDD', 'array VDD strap', 'm2', (vx0 + vx1) / 2, vy0 + 5.00)
gx0, gy0, gx1, _ = apin('VSS')
rect('m1', gx0, 446.00, gx1, gy0 + 1.20)
rect('m1', gx0, 446.00, 456.00, 455.00)
expect('VSS', 'array VSS strap', 'm1', (gx0 + gx1) / 2, gy0 + 5.00)
print(f'array channel: {n_tracks} tracks, row bus x {min(bus_x.values())}-{max(bus_x.values())}')

# ---- seal ring: its three metals are one piece through its via lines and join no other net --------
if SEAL:
    for layer in ('m1', 'm2', 'm3'):
        expect('SEAL', f'seal ring {layer}, west side', layer, 15.00, DIE / 2)

os.makedirs(OUT, exist_ok=True)
gds = os.path.join(OUT, 'pdkv_Top.gds')
ly.write(gds)
with open(os.path.join(OUT, 'pdkv_nets.json'), 'w') as f:
    json.dump({'top': gds, 'blocks': placed, 'nets': nets}, f, indent=1)
print(f'wrote {gds}: bbox {top.dbbox()} um, {len(placed)} blocks, {len(nets)} nets to check')
