"""PDK-layer cells of pdkv that Magic cannot draw with their marker layers (KLayout batch mode).

  pnp10   the PDK vertical PNP (emitter 10 x 10 um), copied unchanged from the kit's
          analog_ETRI/GDS/NSPL_0p5um.gds with its BJT marker (layer 56) and tap subcells
  heater  a poly2 resistor W x L (default 20 x 120 um, 6 squares, about 750 ohm) built with the
          layer set of the PDK p2res cell in the same file: POLY2 13 body, RES 51 over the whole
          resistor, LVSD 60 over the body between the contact heads (sets L), one column of
          0.6 um contacts (CONT 31) under a 1.8 um MET1 head at each end, spaced 1.2 um

The PDK p2res (W 2, L 100 um) puts its contact cut against the LVSD edge, 0.6 um from the POLY2
end and 0.7 um from its sides; the heater keeps those distances (rules 14.PL2PR.E2 >= 0.5,
14.PL2PR.S1 >= 0.6). Both cells go into the chip GDS with the GPIO cells (they already carry
ETRI layer numbers); for LVS they are black boxes with pins.

usage: klayout -b -r designs/etri050/direct/pdk_cells.py -rd kit=<ETRI050_DesignKit> -rd out=<dir>
       [-rd w=20] [-rd l=120]
Pins (um, cell coordinates, metal1): heater A (left head) and B (right head); pnp10 E (centre
square), B (inner ring), C (outer ring).
"""
import os
import pya

kit = globals().get('kit') or os.path.expanduser('~/ETRI050_DesignKit')
out = globals().get('out') or '.'
W = float(globals().get('w') or 20.0)
L = float(globals().get('l') or 120.0)
os.makedirs(out, exist_ok=True)

# ---- pnp10: copy the PDK cell tree ---------------------------------------------------------
src = pya.Layout()
src.read(os.path.join(kit, 'analog_ETRI', 'GDS', 'NSPL_0p5um.gds'))
keep = src.cell('pnp10')
if keep is None:
    raise RuntimeError('pnp10 not found in NSPL_0p5um.gds')
for top in list(src.top_cells()):
    if top.cell_index() != keep.cell_index():
        top.prune_cell()
src.write(os.path.join(out, 'pnp10.gds'))
print(f"pnp10: {keep.dbbox()} um, cells {[c.name for c in src.each_cell()]}")

# ---- heater: poly2 resistor with the p2res layer set ------------------------------------------
ly = pya.Layout()
ly.dbu = 0.001
POLY2, RES, LVSD, CONT, MET1 = (ly.layer(n, 0) for n in (13, 51, 60, 31, 32))
cell = ly.create_cell('heater')
B = lambda x1, y1, x2, y2: pya.DBox(x1, y1, x2, y2)
head, ov = 1.2, 0.8            # POLY2 beyond the LVSD edge, RES beyond POLY2 (as p2res)
x0 = ov
x_l, x_r = ov + head, ov + head + L                   # LVSD edges
x1 = x_r + head
cell.shapes(POLY2).insert(B(x0, ov, x1, ov + W))
cell.shapes(LVSD).insert(B(x_l, 0, x_r, W + 2 * ov))
cell.shapes(RES).insert(B(0, 0, x1 + ov, W + 2 * ov))
cuts = 0
for cx0, mx0 in ((x_l - 0.6, x0), (x_r, x_r - 0.6)):  # cut against the LVSD edge, MET1 head 1.8 um
    cell.shapes(MET1).insert(B(mx0, ov, mx0 + 1.8, ov + W))
    y = ov + 0.7
    while y + 0.6 <= ov + W - 0.7 + 1e-9:
        cell.shapes(CONT).insert(B(cx0, y, cx0 + 0.6, y + 0.6))
        y += 1.2
        cuts += 1
ly.write(os.path.join(out, 'heater.gds'))
sq = L / W
print(f"heater: POLY2 {W:g} x {L:g} um ({sq:g} squares), {cuts // 2} contacts per end, "
      f"cell {cell.dbbox()} um; pins A = MET1 x {x0:g}-{x0 + 1.8:g}, B = MET1 x {x_r - 0.6:g}-{x_r + 1.2:g}")
