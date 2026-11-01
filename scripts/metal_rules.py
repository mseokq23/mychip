"""Contact, metal and via rules (sections 4.7-4.12) as the rule document v1.1 states them (KLayout batch).

The kit's KLayout deck converts these rules with one difference that matters for hand-drawn routing:
it checks VIA1/VIA2 spacing at 0.5 um, while the rule document asks 0.8 um (9.VIA1.S1, 11.VIA2.S1).
This script checks rules 7-12 with the document's values, using the deck's definitions otherwise
(wide metal = the part that survives shrinking by 4.99 um and growing back; MET1/2/3 must touch a
cut; VIA1 must not overlap CONT; VIA2 must not overlap VIA1).

With -rd baseline=<gds>, markers found at the same place in the baseline layout (for the chip: the
pad ring alone, whose ETRI GPIO cells are not ours) are counted apart.

usage: klayout -b -r scripts/metal_rules.py -rd gds=<file.gds> [-rd baseline=<file.gds>] [-rd show=3]
"""
import pya


def check(path):
    ly = pya.Layout()
    ly.read(path)
    top = ly.top_cell()
    um = lambda v: int(round(v / ly.dbu))

    def L(n):
        li = ly.find_layer(n, 0)
        return pya.Region(top.begin_shapes_rec(li)).merged() if li is not None else pya.Region()

    CONT, MET1, VIA1, MET2, VIA2, MET3 = L(31), L(32), L(33), L(34), L(35), L(36)

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
    out = {}
    for rule, v in r.items():
        boxes = [str(item.bbox().to_dtype(ly.dbu)) for item in v.each()]
        if boxes:
            out[rule] = boxes
    return out


found = check(globals()['gds'])
base = check(globals()['baseline']) if globals().get('baseline') else {}
show = int(globals().get('show') or 3)
total = new = 0
for rule, boxes in found.items():
    old = set(base.get(rule, []))
    fresh = [b for b in boxes if b not in old]
    total += len(boxes)
    new += len(fresh)
    note = f" ({len(boxes) - len(fresh)} also in the baseline)" if base else ''
    print(f"  {rule}: {len(boxes)}{note}" + (f"   e.g. {'; '.join(fresh[:show])}" if fresh else ''))
print(f"{globals()['gds'].split('/')[-1]}: {total} markers in rules 7-12 (rule document values)"
      + (f", {new} not in the baseline" if base else ''))
