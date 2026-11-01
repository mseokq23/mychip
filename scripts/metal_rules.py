"""Contact, metal and via rules (sections 4.7-4.12) as the rule document v1.1 states them, and its seal
ring (4.21) when the layout has a chip boundary (KLayout batch).

The kit's KLayout deck converts these rules with one difference that matters for hand-drawn routing:
it checks VIA1/VIA2 spacing at 0.5 um, while the rule document asks 0.8 um (9.VIA1.S1, 11.VIA2.S1).
This script checks rules 7-12 with the document's values, using the deck's definitions otherwise
(wide metal = the part that survives shrinking by 4.99 um and growing back; MET1/2/3 must touch a
cut; VIA1 must not overlap CONT; VIA2 must not overlap VIA1).

Seal ring: as in the deck, the outer 30 um of CHIPBOUNDARY (layer 0) is the seal ring zone and rules
7-12 skip it. Inside it, every layer must be exactly what the 4.21 figure draws (SEAL_FIGURE, the
figure's segments across the ring from its inner side; the metal rows give only the 12 um without
metal toward the scribe lane, so the metal is the other 18 um). Which segments are drawn follows each
layer's digitized-area tone in table 2.1: MET and ACT are digitized dark (the hatched segments), CONT,
VIA and PSD clear (the blank ones). Any other layer in the zone, and anything within 30 um inside it
("Die to Seal ring: 30 um"), is reported too. The deck's own 21.SEAL checks read the first number of
each row as a line width (CONT 4.1, VIA1 6.5, VIA2 4.0, metal 12 um) and so flag the figure's lines.

With -rd baseline=<gds>, markers found at the same place in the baseline layout (for the chip: the
pad ring alone, whose ETRI GPIO cells are not ours) are counted apart.

usage: klayout -b -r scripts/metal_rules.py -rd gds=<file.gds> [-rd baseline=<file.gds>] [-rd show=3]
"""
import pya

RING = 30.0
SEAL_FIGURE = {   # layer: (name, [(segment width um, drawn)]) from the ring's inner (die) edge outward
    11: ('ACT', [(30.0, True)]),
    15: ('PSD', [(30.0, True)]),
    31: ('CONT', [(4.1, False), (0.8, True), (4.2, False), (0.8, True), (4.2, False), (0.8, True), (15.1, False)]),
    32: ('MET1', [(18.0, True), (12.0, False)]),
    33: ('VIA1', [(6.5, False), (1.0, True), (4.0, False), (1.0, True), (17.5, False)]),
    34: ('MET2', [(18.0, True), (12.0, False)]),
    35: ('VIA2', [(4.0, False), (1.0, True), (4.0, False), (1.0, True), (4.0, False), (1.0, True), (15.0, False)]),
    36: ('MET3', [(18.0, True), (12.0, False)]),
}


def check(path):
    ly = pya.Layout()
    ly.read(path)
    top = ly.top_cell()
    um = lambda v: int(round(v / ly.dbu))

    def L(n):
        li = ly.find_layer(n, 0)
        return pya.Region(top.begin_shapes_rec(li)).merged() if li is not None else pya.Region()

    CB = L(0)
    ZONE = CB - CB.sized(-um(RING)) if not CB.is_empty() else pya.Region()
    CONT, MET1, VIA1, MET2, VIA2, MET3 = (L(n) - ZONE for n in (31, 32, 33, 34, 35, 36))

    def wide(m):
        up = m.sized(-um(4.99)).sized(um(4.99))
        return up, m - up

    M1UP, M1UN = wide(MET1)
    M2UP, M2UN = wide(MET2)
    M3UP, M3UN = wide(MET3)

    def size_not(cuts, s):
        bad = pya.Region()
        for p in cuts.each():
            b = p.bbox()
            if not (p.is_box() and b.width() == um(s) and b.height() == um(s)):
                bad.insert(p)
        return bad

    r = {}
    r['7.CONT.W'] = size_not(CONT, 0.6)
    r['7.CONT.S1'] = CONT.space_check(um(0.6))
    r['7.CONT.E.3'] = MET1.enclosing_check(CONT, um(0.6))
    r['7.CONT.bad1'] = CONT - MET1
    r['8.MET1.W'] = MET1.width_check(um(0.8))
    r['8.MET1.S1'] = M1UN.space_check(um(0.8))
    r['8.MET1.S2'] = M1UP.separation_check(MET1, um(1.0))
    r['8.MET1.bad1'] = MET1.not_interacting(CONT + VIA1)
    r['9.VIA1.W'] = size_not(VIA1, 0.8)
    r['9.VIA1.S1'] = VIA1.space_check(um(0.8))
    r['9.VIA1.E1'] = M1UN.enclosing_check(VIA1, um(0.6))
    r['9.VIA1.E3'] = M2UN.enclosing_check(VIA1, um(0.6))
    r['9.VIA1.S'] = VIA1.separation_check(CONT, um(0.6))
    r['9.VIA1.stack'] = VIA1 & CONT
    r['9.VIA1.bad1'] = (VIA1 - MET1) + (VIA1 - MET2)
    r['10.MET2.W'] = MET2.width_check(um(1.0))
    r['10.MET2.S1'] = M2UN.space_check(um(1.0))
    r['10.MET2.S2'] = M2UP.separation_check(MET2, um(1.2))
    r['10.MET2.bad1'] = MET2.not_interacting(VIA1 + VIA2)
    r['11.VIA2.W'] = size_not(VIA2, 0.8)
    r['11.VIA2.S1'] = VIA2.space_check(um(0.8))
    r['11.VIA2.E1'] = M2UN.enclosing_check(VIA2, um(0.6))
    r['11.VIA2.E3'] = M3UN.enclosing_check(VIA2, um(0.6))
    r['11.VIA2.S'] = VIA2.separation_check(VIA1, um(0.6))
    r['11.VIA2.stack'] = VIA2 & VIA1
    r['11.VIA2.bad1'] = (VIA2 - MET2) + (VIA2 - MET3)
    r['12.MET3.W'] = MET3.width_check(um(1.2))
    r['12.MET3.S1'] = M3UN.space_check(um(1.0))
    r['12.MET3.S2'] = M3UP.separation_check(MET3, um(1.2))
    r['12.MET3.bad1'] = MET3.not_interacting(VIA2)

    seal = None
    if not CB.is_empty():
        inner = CB.sized(-um(RING))                     # the ring's inner edge
        for n, (name, segs) in SEAL_FIGURE.items():
            if abs(sum(w for w, _ in segs) - RING) > 1e-9:
                raise RuntimeError(f'{name}: segments do not add up to {RING} um')
            want, a = pya.Region(), 0.0
            for w, drawn in segs:
                if drawn:                               # [a, a + w] from the inner edge
                    want += inner.sized(um(a + w)) - inner.sized(um(a))
                a += w
            want = want & CB
            r[f'21.SEAL.{name}'] = (L(n) & ZONE) ^ want
        others = pya.Region()
        near = CB.sized(-um(RING)) - CB.sized(-um(2 * RING))
        for li in ly.layer_indexes():
            info = ly.get_info(li)
            if info.datatype != 0 or info.layer == 0:
                continue
            reg = pya.Region(top.begin_shapes_rec(li))
            if info.layer not in SEAL_FIGURE:
                others += reg & ZONE
            others += reg & near
        r['21.SEAL.other'] = others
        seal = f'{CB.bbox().to_dtype(ly.dbu)} um, 30 um ring checked against the 4.21 figure'

    out = {}
    for rule, v in r.items():
        boxes = [str(item.bbox().to_dtype(ly.dbu)) for item in v.each()]
        if boxes:
            out[rule] = boxes
    return out, seal


found, seal = check(globals()['gds'])
base = check(globals()['baseline'])[0] if globals().get('baseline') else {}
show = int(globals().get('show') or 3)
total = new = 0
print(f"  chip boundary: {seal or 'none (no layer 0), no seal ring check'}")
for rule, boxes in found.items():
    old = set(base.get(rule, []))
    fresh = [b for b in boxes if b not in old]
    total += len(boxes)
    new += len(fresh)
    note = f" ({len(boxes) - len(fresh)} also in the baseline)" if base else ''
    print(f"  {rule}: {len(boxes)}{note}" + (f"   e.g. {'; '.join(fresh[:show])}" if fresh else ''))
print(f"{globals()['gds'].split('/')[-1]}: {total} markers in rules 7-12" + (" and 4.21" if seal else '')
      + " (rule document values)" + (f", {new} not in the baseline" if base else ''))
