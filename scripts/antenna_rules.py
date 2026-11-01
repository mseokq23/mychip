"""Antenna rules of the rule document v1.1 (KLayout batch): 3.PL1.ANT, 8.MET1.ANT, 10.MET2.ANT, 12.MET3.ANT.

The rule document adds these four in v1.1: field poly to gate poly area at most 200, and MET1, MET2,
MET3 area to the associated gate poly area at most 400, per transistor. The kit's KLayout deck has no
antenna check. ETRI's Calibre deck keeps 3.PL1.ANT and has the three metal rules commented out (its
2023/11/23 revision note); the Assura deck runs all four. Neither gives a diode any credit.

Gate and area layers follow the Calibre deck: GATE = ACT and POLY1, NGATE outside NWELL, PGATE inside;
PAREA/NAREA = the POLY1 polygons that touch a P/N gate. A net's ratio is taken per gate type (its metal
area over its PGATE area, and over its NGATE area, as the deck's macros do) and the larger one counts,
which is stricter than over all its gates (the Assura deck).

Two connectivities, both without diode credit:
  step: what is connected while the layer is etched, in process order: POLY1 alone for the poly rule;
        POLY1, ACT outside the gates, CONT, MET1 for MET1; + VIA1, MET2 for MET2; + VIA2, MET3 for MET3
  full: the finished chip, as the decks' CONNECT statements define their nets
A net over a limit in either is reported, with "diffusion" when it reaches source/drain or tap
diffusion at that step: a junction that drains the charge while the layer is etched, which the rule
document does not count. Power nets are over because of it (much metal, few gates tied to them) and
are tied to diffusion at every step; a net over a limit WITHOUT diffusion at that step is the real
antenna risk, and the summary counts those apart.

With -rd nets=<pdkv_nets.json> (chip assembly), nets are named by the probe points of the routing.

usage: klayout -b -r scripts/antenna_rules.py -rd gds=<file.gds> [-rd nets=<nets.json>] [-rd show=3]
"""
import json
import pya

LIMIT = {'3.PL1.ANT': 200.0, '8.MET1.ANT': 400.0, '10.MET2.ANT': 400.0, '12.MET3.ANT': 400.0}
METAL = {'3.PL1.ANT': 'poly', '8.MET1.ANT': 'm1', '10.MET2.ANT': 'm2', '12.MET3.ANT': 'm3'}
NUM = {'act': 11, 'poly': 12, 'nwell': 2, 'cont': 31, 'm1': 32, 'v1': 33, 'm2': 34, 'v2': 35, 'm3': 36}
ORDER = ['m1', 'm2', 'm3']
RUNS = (('step', None, ['3.PL1.ANT']), ('step', 'm1', ['8.MET1.ANT']), ('step', 'm2', ['10.MET2.ANT']),
        ('full', 'm3', list(LIMIT)))      # step for MET3 is the finished chip


def extract(ly, cell, upto):
    """Nets of POLY1 (upto None) or of POLY1, diffusion and metal up to <upto> ('m1', 'm2', 'm3')."""
    l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, cell, []))

    def lay(name):
        li = ly.find_layer(NUM[name], 0)
        return l2n.make_layer(li if li is not None else ly.layer(NUM[name], 0), name)

    poly, act, nwell = lay('poly'), lay('act'), lay('nwell')
    gate = act & poly
    ngate, pgate = gate - nwell, gate & nwell
    l2n.register(ngate, 'ngate')
    l2n.register(pgate, 'pgate')
    for g in (ngate, pgate):
        l2n.connect(g)
        l2n.connect(g, poly)
    l2n.connect(poly)
    regs = {'poly': poly, 'ngate': ngate, 'pgate': pgate}
    if upto:
        sd = act - poly
        l2n.register(sd, 'sd')
        regs['sd'] = sd
        cont = lay('cont')
        l2n.connect(sd)
        l2n.connect(cont)
        l2n.connect(cont, sd)
        l2n.connect(cont, poly)
        below = cont
        for m in ORDER[:ORDER.index(upto) + 1]:
            regs[m] = lay(m)
            l2n.connect(regs[m])
            l2n.connect(below, regs[m])
            if m != upto:
                v = lay({'m1': 'v1', 'm2': 'v2'}[m])
                l2n.connect(v)
                l2n.connect(regs[m], v)
                below = v
    l2n.extract_netlist()
    return l2n, regs


def net_names(l2n, regs, spec):
    names = {}
    for name, probes in (spec or {}).get('nets', {}).items():
        for p in probes:
            if p['layer'] in regs:
                n = l2n.probe_net(regs[p['layer']], pya.DPoint(p['x'], p['y']))
                if n is not None:
                    names.setdefault(n.cluster_id, set()).add(name)
    return names


def ratios(ly, l2n, regs, rules, names):
    """[(ratio, rule, gate type, net box, diffusion, name)]: per net and rule, the larger per-type ratio."""
    out = []
    for net in next(l2n.netlist().each_circuit_top_down()).each_net():
        gates = {t: l2n.shapes_of_net(net, regs[k], True) for t, k in (('N', 'ngate'), ('P', 'pgate'))}
        if gates['N'].is_empty() and gates['P'].is_empty():
            continue
        diff = 'sd' in regs and not l2n.shapes_of_net(net, regs['sd'], True).is_empty()
        name = '/'.join(sorted(names.get(net.cluster_id, [])))
        for rule in rules:
            shapes = l2n.shapes_of_net(net, regs[METAL[rule]], True)
            best = None
            for t, g in gates.items():
                if g.is_empty():
                    continue
                a = shapes.interacting(g).area() if rule == '3.PL1.ANT' else shapes.area()
                r = a / g.area()
                if best is None or r > best[0]:
                    best = (r, t)
            out.append((best[0], rule, best[1], str(shapes.bbox().to_dtype(ly.dbu)), diff, name))
    return out


def main(path, show, spec):
    ly = pya.Layout()
    ly.read(path)
    top = ly.top_cell()
    ly.flatten(top.cell_index(), -1, True)
    found = {r: [] for r in LIMIT}
    for mode, upto, rules in RUNS:
        l2n, regs = extract(ly, top, upto)
        names = net_names(l2n, regs, spec)
        for ratio, rule, t, box, diff, name in ratios(ly, l2n, regs, rules, names):
            m = 'step/full' if (mode, rule) == ('full', '12.MET3.ANT') else mode
            found[rule].append((ratio, m, t, box, diff, name))

    def fmt(i):
        r, m, t, b, d, name = i
        return f"{r:.0f} ({m}, {t}GATE{', diffusion' if d else ''}) {name or 'at ' + b}"

    total = bare = 0
    for rule, items in found.items():
        items = sorted((i for i in items if i[0] > 0), key=lambda i: -i[0])     # nets with that layer
        key = lambda i: i[5] or i[3]          # a net: its name, else its metal's extent
        over, seen = [], set()
        for i in items:                       # each net once, with its largest ratio
            if i[0] > LIMIT[rule] and key(i) not in seen:
                seen.add(key(i))
                over.append(i)
        bad = {key(i) for i in items if i[0] > LIMIT[rule] and not i[4]}
        total += len(over)
        bare += len(bad)
        line = f"  {rule} (limit {LIMIT[rule]:.0f}): {len(over)} over"
        if over:
            line += (f" ({len(bad)} without diffusion): {'; '.join(fmt(i) for i in over[:show])}"
                     + (' ...' if len(over) > show else ''))
        largest = [i for i in items if i[0] <= LIMIT[rule] and key(i) not in seen][:1]
        if largest:
            line += f"; largest under the limit {fmt(largest[0])}"
        nodiff = [i for i in items if not i[4] and i[0] <= LIMIT[rule]][:1]
        if nodiff and nodiff[0] not in largest:
            line += f"; largest without diffusion {fmt(nodiff[0])}"
        print(line)
    print(f"{path.split('/')[-1]}: {total} nets over the antenna limits (rule document v1.1, no diode credit),"
          f" {bare} without diffusion at that step")


main(globals()['gds'], int(globals().get('show') or 3),
     json.load(open(globals()['nets'])) if globals().get('nets') else None)
