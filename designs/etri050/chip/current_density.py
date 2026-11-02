#!/usr/bin/env python3
"""DC current density on the chip's force and heater paths: which narrow piece of metal carries how much.

The rule document has no metal current limit; the design assumes J = 1 mA/um (ETRI question 4). For
every net that carries a measurement or heater current, from the pad (or the column switch) to the
device at the far end:

  1. every piece of the net's metal narrower than I / J (I the net's largest current) is found with a
     width check on each metal layer
  2. the current distribution for each device the net can feed comes from KLayout's resistance
     extractor (klayout.pex: metal and vias, rule document 5.2 / 5.3 typical values) with every
     current contact a port: a device's contacts are joined through their contact resistance to one
     node per active area (a transistor with its fingers) or resistor head; the current enters at the
     force port's metal2 and leaves at that node
  3. each narrow piece is cut out of its polygon in turn: the current through it is what the current
     contacts beyond the cut draw (Kirchhoff), J = I / w with w its width. A cut that leaves no
     current contact beyond it passes nothing (a sense line, a stub); a cut that separates nothing
     has a parallel path and is listed with I / w as its bound

  4. each group of via cuts between the same two pieces of metal is left out the same way: its current
     over its number of cuts is the current per cut (exact for one cut, the average for an array);
     each contact's current comes from the solved network. The rule document has no cut limit either;
     a cut is taken to carry J x its width (VIA1 / VIA2 0.8 um: 0.8 mA, CONT 0.6 um: 0.6 mA)

Current terminals are the force port and the contacts on source / drain diffusion and resistor heads;
sense ports (PANA PADR: a voltmeter), taps and gate contacts carry no DC current. A transmission gate's
NMOS and PMOS are taken each as carrying the whole current alone: a column's force switch feeds its
cells through the NMOS and, as another case, through the PMOS; the parking switches (off while their
column is selected) carry none. A piece that some slice puts in series takes its largest series
current; a piece that no slice separates is a parallel path, listed with I / w as a bound (never
counted: the port landings, where the current crosses the 9 um side, are the two today).

  case          net          mA   in at                         out at (each in turn)
  ADF           ADF          5    W3 ADF (PAD)                  each column's force switch, NMOS or PMOS
  D0 - D7       array.D<c>   5    the column's force switch     each cell of the column
  SRC           SRC          5    W5 ASF (PAD)                  each cell
  D1, D2        D1, D2       5    N2 LD1F, N6 LD2F              the L-split device
  S             S            7    N4 LSF                        both L-split devices (shared source)
  HT            HT           7    E7 HT (PAD)                   heater head A
  heater return VSS          7    heater head B                 E5 PVSS, through VSS's own heater branch

usage: python3 designs/etri050/chip/current_density.py [--gds build/pdkv_Top.gds] [--limit 1.0]
       exit 0 when no piece in series and no cut exceeds its limit
"""
import argparse
import collections
import re
import sys
from pathlib import Path

import numpy as np
import klayout.db as kdb
import klayout.pex as pex

import chip_lvs

HERE = Path(__file__).resolve().parent
RS = {"m1": 0.08, "m2": 0.08, "m3": 0.05}                 # ohm/sq, rule document 5.2 typ
RCUT = {"v1": 2.0, "v2": 1.5}                              # ohm per cut, 5.3 typ
RCONT = {"n": 30.0, "p": 90.0, "poly2": 50.0}              # ohm per contact, 5.3 typ
CUT_AREA = 0.64                                            # um2: VIA1 / VIA2 cuts are 0.8 x 0.8 um
CUT_W = {"v1": 0.8, "v2": 0.8, "cont": 0.6}                # um: cut widths (limit per cut = J x width)
LAYER_ID = {"m1": 1, "m2": 2, "m3": 3, "v1": 11, "v2": 12}
METALS = ("m1", "m2", "m3")
VIAS = (("v1", "m1", "m2"), ("v2", "m2", "m3"))
SWITCH_W = 50.0                                            # um: force switch fingers (100.8 / 252 um)
# the most a device under test can draw per um of gate width: rule document 5.1 Idsat maxima (600 / 310
# uA/um at 5 V, L 0.5 um) plus 20 % for 5.5 V and the fast corner; a narrow cell never takes the full 5 mA
JSAT = {"n": 0.72, "p": 0.37}                              # mA/um
CASES = [  # (label, chip net, mA, in: pad pin or group kind, out: group kind or pad pin)
    ("ADF", "ADF", 5.0, "ADF", "switch"),
    *[(f"array.D{c}", f"array.D{c}", 5.0, "switch", "cell") for c in range(8)],
    ("SRC", "SRC", 5.0, "ASF", "cell"),
    ("D1", "D1", 5.0, "LD1F", "cell"),
    ("D2", "D2", 5.0, "LD2F", "cell"),
    ("S", "S", 7.0, "LSF", "cells"),
    ("HT", "HT", 7.0, "HT", "heater"),
    ("heater return", "VSS", 7.0, "heater", "PVSS"),
]


def overlaps(a, b):
    return a.bbox().overlaps(b.bbox()) and not (kdb.Region(a) & kdb.Region(b)).is_empty()


class Metal:
    """A net's metal as polygons per layer, joined by its via cuts, with terminals on it: connected
    components, also with one polygon cut."""

    def __init__(self, geo, terms, wide=()):
        """terms: [(layer, polygon)]; wide: indices of terminals that join every piece they touch (pad
        ports); a via or a contact belongs to the piece under its centre."""
        self.wide = set(wide)
        self.poly = {k: list(geo[k].each()) for k in METALS}
        self.box = {k: np.array([[p.bbox().left, p.bbox().bottom, p.bbox().right, p.bbox().top]
                                 for p in self.poly[k]] or np.zeros((0, 4))) for k in METALS}
        self.vshape = [(lo, hi, c) for v, lo, hi in VIAS for c in geo[v].each()]
        self.vias = [[(k, i) for k in (lo, hi) for i in self.on(k, c)] for lo, hi, c in self.vshape]
        self.terms = terms
        self.tpoly = [[(k, i) for i in self.on(k, s)] for k, s in terms]

    def on(self, k, shape):
        b = shape.bbox()
        x = self.box[k]
        cand = np.nonzero((x[:, 0] <= b.right) & (x[:, 2] >= b.left) & (x[:, 1] <= b.top) & (x[:, 3] >= b.bottom))[0]
        return [int(i) for i in cand if overlaps(self.poly[k][i], shape)]

    def components(self, cut=None, skip=()):
        """([component of each terminal], number of components). cut = (layer, polygon, region); skip:
        indices of via cuts left out."""
        nodes = {(k, i): n for n, (k, i) in enumerate((k, i) for k in METALS for i in range(len(self.poly[k])))}
        parent = list(range(len(nodes)))
        pieces = []
        if cut:
            k, i, q = cut
            pieces = list((kdb.Region(self.poly[k][i]) - q).each())
            for j in range(len(pieces)):
                nodes[(k, i, j)] = len(parent)
                parent.append(len(parent))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def ends(where, shape, wide=False):
            out = []
            for k, i in where:
                if cut and (k, i) == cut[:2]:
                    if wide:
                        out += [nodes[(k, i, j)] for j, p in enumerate(pieces) if overlaps(p, shape)]
                    else:
                        c = shape.bbox().center()
                        at = [j for j, p in enumerate(pieces) if p.inside(c)]
                        if not at:                         # the centre in the cut itself: the larger part
                            area = [(kdb.Region(p) & kdb.Region(shape)).area() for p in pieces]
                            at = [max(range(len(pieces)), key=area.__getitem__)] if pieces and max(area) > 0 else []
                        out += [nodes[(k, i, j)] for j in at]
                else:
                    out.append(nodes[(k, i)])
            return out

        live = [n for key, n in nodes.items() if not (cut and key == cut[:2])]
        for v, (where, (lo, hi, c)) in enumerate(zip(self.vias, self.vshape)):
            if v in skip:
                continue
            e = ends(where, c)
            for x in e[1:]:
                parent[find(x)] = find(e[0])
        comp = []
        for t, ((k, s), where) in enumerate(zip(self.terms, self.tpoly)):
            e = ends(where, s, t in self.wide)
            for x in e[1:]:
                parent[find(x)] = find(e[0])
            comp.append(e[0] if e else None)
        comp = [find(x) if x is not None else None for x in comp]
        return comp, len({find(n) for n in live})

    def clusters(self):
        """{the metal pieces a group of via cuts joins: [cut index]}: the cuts between the same pieces."""
        out = collections.defaultdict(list)
        for v, where in enumerate(self.vias):
            if len({k for k, i in where}) == 2:
                out[tuple(sorted(where))].append(v)
        return out


def through(I, comp, nc, n0, ma):
    """The current through a removed part: what the terminals on one side draw ((mA, "series")), nothing
    when the removal only cuts off metal without terminals, else a parallel path ((ma, "parallel"))."""
    sides = collections.defaultdict(list)
    for t, c in enumerate(comp):
        sides[c].append(t)
    if len(sides) == 1:
        return (0.0, "dead end") if nc > n0 else (ma, "parallel")
    return max(np.abs(I[ts].sum(axis=0)).max() for ts in sides.values()) * 1e3, "series"


def analyse(keep, case, limit, pins):
    label, netname, ma, src, dst = case
    lv, L, ly, names = keep["lv"], keep["L"], keep["ly"], keep["names"]
    um = ly.dbu
    circ = next(lv.netlist().each_circuit_top_down())
    net = next(n for n in circ.each_net() if names.get(n.cluster_id) == netname)
    geo = {k: lv.shapes_of_net(net, L[k], True).merged() for k in ("m1", "m2", "m3", "v1", "v2", "cont")}
    # current contacts, grouped by active area (transistors) or resistor head
    groups = collections.defaultdict(list)                 # key -> [(contact, ohm)]
    act = kdb.Region([p for p in L["act"].each()]).merged()
    for kind in ("n", "p"):
        sd = lv.shapes_of_net(net, lv.layer_by_name(f"{kind}isd"), True).merged()
        cont = geo["cont"] & sd
        for a in act.interacting(cont).each():
            for c in cont.interacting(kdb.Region(a)).each():
                groups[("mos", kind, a.bbox())].append((c, RCONT[kind]))
    for h in lv.shapes_of_net(net, lv.layer_by_name("r_term"), True).merged().each():
        for c in (geo["cont"] & kdb.Region(h)).each():
            groups[("head", "poly2", h.bbox())].append((c, RCONT["poly2"]))
    # what each group is: a column force switch, a parking switch, a heater head, a device under test
    gate = L["poly1"] & L["act"]
    pl1 = lv.layer_by_name("pl1")

    def kind(key):
        if key[0] == "head":
            return "heater" if max(key[2].width(), key[2].height()) * um > 15 else "head"
        area = kdb.Region(kdb.Box(key[2]))
        gs = list((gate & area).each())
        nets = set()
        for g in gs:
            c = g.bbox().center()
            n = lv.probe_net(pl1, kdb.DPoint(c.x * um, c.y * um))
            nets.add(names.get(n.cluster_id, "?") if n else "?")
        w = sum(max(g.bbox().width(), g.bbox().height()) for g in gs) * um
        if any(re.match(r"COL_SELB?\d+$", n) for n in nets):
            return "switch" if w >= SWITCH_W else "park"
        if any(re.match(r"array\.G\d+$", n) or n == "LG" for n in nets):
            cap[key] = min(ma, JSAT[key[1]] * w)
            return "cell"
        return "other"                                     # sense switches: no current

    cap = {}
    kinds = {k: kind(k) for k in groups}
    if netname == "VSS":                                   # the heater's own branch of VSS
        heads = [k for k in groups if kinds[k] == "heater"]
        polys = [(k, p) for k in METALS for p in geo[k].each()]
        m = Metal(geo, [("m1", groups[k][0][0]) for k in heads] + polys)
        comp, _ = m.components()
        sub = {k: kdb.Region() for k in geo}
        for (k, p), c in zip(polys, comp[len(heads):]):
            if c == comp[0]:
                sub[k].insert(p)
        for v in ("v1", "v2", "cont"):
            sub[v] = geo[v].interacting(sub["m1"] + sub["m2"] + sub["m3"])
        geo = sub
        groups = {k: groups[k] for k in heads}
        kinds = {k: "heater" for k in heads}
    pads = [kdb.Polygon(kdb.DBox(*rect).to_itype(um)) for name, chipnet, pad, rect, port in pins
            if chipnet == netname and name in (src, dst)]
    pads = [p for p in pads if not (geo["m2"] & kdb.Region(p)).is_empty()]
    contacts = [(key, c, r) for key in groups if kinds[key] not in ("park", "other") for c, r in groups[key]]
    t = pex.RExtractorTech()
    for k in METALS:
        c = pex.RExtractorTechConductor()
        c.layer, c.resistance = LAYER_ID[k], RS[k]
        if k == "m3":                                      # plates: 2-D spreading
            c.algorithm = pex.Algorithm.Tesselation
            c.triangulation_max_area = 20.0
            c.triangulation_min_b = 1.0
        t.add_conductor(c)
    for v, lo, hi in VIAS:
        x = pex.RExtractorTechVia()
        x.cut_layer, x.bottom_conductor, x.top_conductor = LAYER_ID[v], LAYER_ID[lo], LAYER_ID[hi]
        x.resistance = RCUT[v] * CUT_AREA
        t.add_via(x)
    rn = pex.RNetExtractor(um).extract(t, {LAYER_ID[k]: geo[k] for k in ("m1", "m2", "m3", "v1", "v2")}, {},
                                       {1: [c for _, c, _ in contacts], 2: pads})
    idx, port = {}, {}
    for nd in rn.each_node():
        idx[nd.object_id()] = len(idx)
        if nd.type() == pex.RNode.PolygonPort:
            port[(nd.layer(), nd.port_index())] = idx[nd.object_id()]
    keys = sorted({key for key, _, _ in contacts}, key=str)
    gnode = {k: len(idx) + j for j, k in enumerate(keys)}
    n = len(idx) + len(keys)
    G = np.zeros((n, n))

    def add(a, b, r):
        g = 1.0 / max(r, 1e-6)
        G[a, a] += g
        G[b, b] += g
        G[a, b] -= g
        G[b, a] -= g

    for e in rn.each_element():
        add(idx[e.a().object_id()], idx[e.b().object_id()], e.resistance())
    for j, (key, c, r) in enumerate(contacts):
        add(port[(1, j)], gnode[key], r)
    # in: a pad port (ground), or each source group alone (the NMOS and the PMOS of the column's force
    # transmission gate each carrying the whole current); out: the scenarios
    if src in kinds.values():
        ins = [[gnode[k]] for k in keys if kinds[k] == src]
    else:
        ins = [[port[(2, j)] for j in range(len(pads))]]
    if not ins or not all(ins):
        raise SystemExit(f"{label}: no way in")
    if dst == "PVSS":
        outs = [[port[(2, j)] for j in range(len(pads))]]
    elif dst == "cells":
        outs = [[gnode[k] for k in keys if kinds[k] == "cell"]]
    else:
        outs = [[gnode[k]] for k in keys if kinds[k] == dst]
    if not outs or not all(outs):
        return None, 0, 0.0, 0.0                           # nothing to feed (array column 7 has no cells)
    at = {gnode[k]: k for k in keys}
    cols = []
    for inn in ins:
        G1 = G.copy()
        for x in inn[1:]:
            G1[inn[0], inn[0]] += 1e6
            G1[x, x] += 1e6
            G1[inn[0], x] -= 1e6
            G1[x, inn[0]] -= 1e6
        keepn = [i for i in range(n) if i != inn[0]]
        pos = {k: j for j, k in enumerate(keepn)}
        B = np.zeros((len(keepn), len(outs)))
        for sc, out in enumerate(outs):
            for x in out:                                  # a device: what it can draw; together: the case's
                each = cap.get(at.get(x), ma) if len(out) == 1 else ma / len(out)
                B[pos[x], sc] += each * 1e-3
        V = np.zeros((n, len(outs)))
        V[keepn] = np.linalg.solve(G1[np.ix_(keepn, keepn)], B)
        # each contact's current out of the metal, per scenario; the pads' as the balance
        Iv = np.array([(V[port[(1, j)]] - V[gnode[key]]) / r for j, (key, c, r) in enumerate(contacts)]
                      + [np.zeros(len(outs))] * len(pads))
        if pads:
            Iv[len(contacts):] = -Iv[:len(contacts)].sum(axis=0) / len(pads)
        cols.append(Iv)
    I = np.hstack(cols)
    terms = [("m1", c) for _, c, _ in contacts] + [("m2", p) for p in pads]
    metal = Metal(geo, terms, wide=range(len(contacts), len(terms)))
    comp0, n0 = metal.components()
    rows = []
    for k in METALS:
        for ep in geo[k].width_check(round(ma / limit / um), False, kdb.Region.Projection).each():
            hit = metal.on(k, ep.polygon(0))
            if not hit:
                continue
            w = ep.distance() * um
            got = [through(I, *metal.components((k, hit[0], q)), n0=n0, ma=ma) for q in slices(ep)]
            # the terminals on each side of a slice draw their current through it; a slice in series
            # decides, else the piece is a parallel path (a bound) or a dead end
            series = [g for g in got if g[1] == "series"]
            best = max(series) if series else max(got)
            c = ep.bbox().center()
            rows.append((best[0] / w, label, k, w, best[0], best[1], c.x * um, c.y * um))
    # via cuts: each group of cuts between the same two pieces is left out in turn, as a slice is
    cuts = []
    for group in metal.clusters().values():
        cur, how = through(I, *metal.components(skip=set(group)), n0=n0, ma=ma)
        b = kdb.Box()
        for v in group:
            b += metal.vshape[v][2].bbox()
        layer = next(v for v, lo, hi in VIAS if (lo, hi) == metal.vshape[group[0]][:2])
        cuts.append((cur / len(group), label, layer, len(group), cur, how, b.center().x * um, b.center().y * um))
    conts = [(abs(I[j]).max() * 1e3, label, "cont", 1, abs(I[j]).max() * 1e3, "series",
              c.bbox().center().x * um, c.bbox().center().y * um) for j, (key, c, r) in enumerate(contacts)]
    return rows, len(outs) * len(ins), cuts, conts


def slices(ep, d=20, step=500):
    """Thin bands (d dbu) across a width check's edge pair, at both ends of the facing part and every
    step dbu between: what crosses a band flows along the edges."""
    e1, e2 = ep.first, ep.second
    v = kdb.DVector(e1.p2 - e1.p1)
    n = v.length()
    if n <= 2 * d:
        return [kdb.Region(ep.polygon(0))]
    u = v * (1.0 / n)
    out = []
    k = max(1, int((n - 2 * d) // step))
    for s in [d + (n - 2 * d) * j / k for j in range(k + 1)]:
        a = kdb.DPoint(e1.p1) + u * s
        b0 = kdb.DPoint(e2.p1)
        w = kdb.DVector(e2.p2 - e2.p1)
        t = ((a - b0).x * w.x + (a - b0).y * w.y) / max(w.sq_length(), 1e-9)
        b = b0 + w * t
        h = u * (d / 2)
        out.append(kdb.Region(kdb.DPolygon([a - h, a + h, b + h, b - h]).to_itype(1.0)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    ap.add_argument("--limit", type=float, default=1.0, help="mA/um")
    a = ap.parse_args(argv)
    good, rep, nl, keep = chip_lvs.lvs(a.gds, named=True, keep=True)
    if not good:
        print("\n".join(rep))
        return 1
    pins = chip_lvs.pad_pins()
    cut_limit = {k: a.limit * w for k, w in CUT_W.items()}
    bad, bad_cuts = [], []
    for case in CASES:
        rows, ns, cuts, conts = analyse(keep, case, a.limit, pins)
        if rows is None:
            print(f"{case[0]}: no device to feed")
            continue
        cnt = collections.Counter(r[5] for r in rows)
        series = sorted((r for r in rows if r[5] == "series"), reverse=True)
        par = [r for r in rows if r[5] == "parallel"]
        s = series[0] if series else None
        vs = sorted((c for c in cuts if c[5] == "series"), reverse=True)
        v = vs[0] if vs else None
        c = max(conts) if conts else None
        print(f"{case[0]}: {case[2]:g} mA, {ns} case(s), {len(rows)} narrow pieces ({', '.join(f'{k} {v}' for k, v in sorted(cnt.items()))}); "
              + (f"worst {s[0]:.2f} mA/um: {s[2]} {s[3]:.2f} um, {s[4]:.2f} mA at ({s[6]:.1f}, {s[7]:.1f})" if s else "no series piece")
              + (f"; parallel bound up to {max(r[0] for r in par):.2f} mA/um" if par else "")
              + (f"; via cuts: most {v[0]:.2f} mA per cut ({v[2]} x{v[3]}, {v[4]:.2f} mA at ({v[6]:.1f}, {v[7]:.1f}))" if v else "")
              + (f"; most per contact {c[0]:.2f} mA" if c else ""))
        bad += [r for r in series if r[0] > a.limit]
        bad_cuts += [x for x in vs if x[0] > cut_limit[x[2]]] + [x for x in conts if x[0] > cut_limit["cont"]]
        for r in par:
            if r[0] > a.limit:
                print(f"    parallel: {r[2]} {r[3]:.2f} um at ({r[6]:.1f}, {r[7]:.1f})")
    print(f"pieces in series over {a.limit:g} mA/um: {len(bad)}")
    kinds = collections.defaultdict(list)
    for j, label, k, w, ic, how, x, y in bad:
        kinds[(re.sub(r"\d$", "<c>", label) if label.startswith("array.") else label, k, round(w, 2), round(ic, 2))].append((x, y))
    for (label, k, w, ic), at in sorted(kinds.items(), key=lambda kv: -kv[0][3] / kv[0][2]):
        print(f"  {label}: {k} {w:.2f} um, {ic:.2f} mA -> {ic / w:.2f} mA/um, {len(at)} place(s), e.g. ({at[0][0]:.1f}, {at[0][1]:.1f})")
    print(f"cuts over {a.limit:g} mA/um x cut width (VIA1 / VIA2 {cut_limit['v1']:g} mA, CONT {cut_limit['cont']:g} mA, "
          f"an assumption like the metal's): {len(bad_cuts)}")
    kinds = collections.defaultdict(list)
    for per, label, k, n, ic, how, x, y in bad_cuts:
        kinds[(re.sub(r"\d$", "<c>", label) if label.startswith("array.") else label, k, n)].append((per, x, y))
    for (label, k, n), at in sorted(kinds.items(), key=lambda kv: -max(kv[1])[0]):
        top = max(at)
        print(f"  {label}: {k} x{n}, {min(at)[0]:.2f}-{top[0]:.2f} mA per cut, {len(at)} place(s), "
              f"most at ({top[1]:.1f}, {top[2]:.1f})")
    return 0 if not bad and not bad_cuts else 1


if __name__ == "__main__":
    sys.exit(main())
