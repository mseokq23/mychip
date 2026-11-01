#!/usr/bin/env python3
"""Expected CBCM capacitances of the drawn block, from the rule document's capacitance table.

For cell i the CBCM reads (I(VCD) - I(VCR)) / (V f) = C(ND<i>) - C(NR<i>): both nodes carry the same
pseudo-inverter pair, ND<i> also its structure and the lead to it. This script takes the two nodes of
every cell from build/cbcm_full.gds (KLayout connectivity; net names from the generator's drawn
rectangles, so a short or an open in a node stops it), and sums, per neighbouring net, the area and
fringe capacitance of every overlap with the values of the rule document v1.1:

  5.5 Parasitic Interconnect Capacitance (area fF/um2, fringe fF/um), the only values given (typical)
  5.4 Poly Capacitance, POLY2 to POLY1: 0.45 / 0.50 / 0.55 fF/um2 (min / typ / max)

How the table is applied
  area    a conductor's area over the nearest conductor below it (any net; the same net counts nothing),
          "field" where there is none: p-substrate (VSS) or the N-well's net
  fringe  the conductor's edge where the nearest conductor below continues just outside the edge
          (5 nm strip), field fringe where there is none
  both    a node's shape under another net's conductor counts from that conductor's side (M2 over the
          node's M1: "Metal 2 to Metal 1" area and the M2 edges over it)
  gate    poly over active: the gate value of the body's type (NMOS outside the N-well), area to the
          body net; gate fringe along the poly edges over source / drain, to the source / drain net
  diff    n+ outside the N-well to the substrate (VSS), p+ inside it to the well's net: area and the
          perimeter that does not face a gate ("N+ Diffusion to P-Well", "P+ Diffusion to N-Well")
  PIP     POLY2 over POLY1: 5.4 typ; its edges: PDK pipcap_i CAPSW 9e-11 F/m (the document has no value)
Not in the document: coupling between neighbours on the same layer. It is listed as the facing length
(edge pairs closer than 3 um) per neighbour; the MET1 comb (cell 5) measures it at 0.9 um.

During the measurement of cell i the clock nets switch (clk, the generator's nodes, PCK, NG) and so
do PG<i>, ND<i> and NR<i>; everything else is held (supplies, en, the other cells' nodes) and is a
capacitance to AC ground. The table splits each node's sum into these two parts.

usage: python3 designs/etri050/cbcm/cbcm_c.py [--gds build/cbcm_full.gds]
       writes build/cbcm_c.json (every coupling of ND<i> and NR<i>) and cbcm_c.csv (per cell)
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gen"))
import etri050_cbcm as gen  # noqa: E402

GDS_NUM = {"nwell": 2, "act": 11, "poly": 12, "poly2": 13, "nsd": 14, "psd": 15,
           "cont": 31, "m1": 32, "v1": 33, "m2": 34, "v2": 35, "m3": 36}
# rule document v1.1, 5.5 (typical): (area fF/um2, fringe fF/um); "pa" = poly or active
DOC = {("ndiff", "field"): (0.6882, 0.3212), ("pdiff", "field"): (0.7933, 0.2277),
       ("ngate", "chan"): (2.9739, 0.3134), ("pgate", "chan"): (2.9624, 0.2138),
       ("poly", "field"): (0.0902, 0.0519),
       ("m1", "field"): (0.0435, 0.0551), ("m1", "pa"): (0.0703, 0.0657),
       ("m2", "field"): (0.0241, 0.0406), ("m2", "pa"): (0.0299, 0.0437), ("m2", "m1"): (0.0446, 0.0487),
       ("m3", "field"): (0.0165, 0.0332), ("m3", "pa"): (0.0188, 0.0353), ("m3", "m1"): (0.0222, 0.0361),
       ("m3", "m2"): (0.0422, 0.0479),
       ("poly2", "poly"): (0.50, 0.09)}    # 5.4 typ; fringe = PDK pipcap_i CAPSW (not in the document)
STACK = ["m3", "m2", "m1", "poly2", "poly", "diff"]        # conductors, top to bottom; field below
GROUP = {"m2": "m2", "m1": "m1", "poly2": "pa", "poly": "pa", "diff": "pa"}
STRIP = 0.005                                                # um, outside strip that finds an edge's lower plate
FACE = 3.0                                                   # um, facing-length search distance

SWITCHING = {"clk", "clkb", "p1", "p2", "p1n", "p2n", "d1", "d2", "PCK", "NG"} | \
    {f"{t}{k}" for t in "ab" for k in range(1, gen.NDELAY)}


def body_windows():
    """Structure body (um boxes, block coordinates) per cell, for the body / lead split."""
    um = lambda *v: tuple(round(x * gen.LAMBDA_UM, 4) for x in v)
    px, py = gen.PIP_UM
    w = {1: (px, py, px + 34.4, py + 32.4)}
    for i in (2, 3, 4):
        xa, xb = gen.PLATE[i]
        w[i] = um(xa - 0.5, gen.Y_TOP0 - 3, xb + 0.5, gen.H)
    w[5] = um(gen.COMB_X[0] - 0.5, -4, gen.COMB_X[1] + 0.5, gen.Y_BOT1 - 4)
    w[6] = um(389 - 0.5, gen.NAREA_Y - 0.5, 389 + 67.5, gen.NAREA_Y + 67.5)
    w[7] = um(500 - 0.5, gen.NEDGE_Y - 0.5, 500 + 14 * 9 - 5.5, gen.NEDGE_Y + 56.5)
    for i, gx, nf, l in ((8, 165, 1, round(gen.GATE_L10[1] / gen.LAMBDA_UM)),
                         (9, 259, gen.GATE_L2[2], round(gen.GATE_L2[1] / gen.LAMBDA_UM))):
        xa = gx + 6 + 2 + l + 2 + 6 if nf == 1 else gx + nf * (l + 10) + 6
        w[i] = um(gx - 0.5, gen.GATE_Y - 2.5, xa + 0.5, gen.GATE_Y + 160 + 9.5)
    return w


def band_window(i):
    """The pseudo-inverter pair of cell i (um box)."""
    band, x0 = gen.PAIRS[i]
    y0, y1 = gen.band_y(band == "upper", (-4, gen.BAND_TOP))
    return tuple(round(v * gen.LAMBDA_UM, 4) for v in (x0 + gen.PAIR_X[0], y0, x0 + gen.PAIR_X[1], y1))


class Extract:
    def __init__(self, gds):
        self.ly = kdb.Layout()
        self.ly.read(str(gds))
        self.top = self.ly.top_cell()
        self.dbu = self.ly.dbu
        l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(self.ly, self.top, []))
        L = {k: l2n.make_layer(self.ly.layer(n, 0), k) for k, n in GDS_NUM.items()}
        sd = L["act"] - L["poly"]
        ndiff, pdiff = sd & L["nsd"], sd & L["psd"]
        ptap = pdiff - L["nwell"]
        c2 = L["cont"] & L["poly2"]          # a contact on POLY2 lands on POLY2, not on the POLY1 under it
        c1 = L["cont"] - L["poly2"]
        for name, reg in (("ndiff", ndiff), ("pdiff", pdiff), ("ptap", ptap), ("c1", c1), ("c2", c2)):
            l2n.register(reg, name)
        for reg in (ndiff, pdiff, L["poly"], L["poly2"], L["m1"], L["m2"], L["m3"], L["nwell"], c1, c2,
                    L["v1"], L["v2"], ptap):
            l2n.connect(reg)
        for a, b in ((c1, ndiff), (c1, pdiff), (c1, L["poly"]), (c1, L["m1"]), (c2, L["poly2"]),
                     (c2, L["m1"]), (L["m1"], L["v1"]), (L["v1"], L["m2"]), (L["m2"], L["v2"]),
                     (L["v2"], L["m3"]), (ndiff, L["nwell"]), (pdiff, ptap)):
            l2n.connect(a, b)
        l2n.connect_global(ptap, "SUB")
        l2n.extract_netlist()
        self.l2n, self.L = l2n, L
        self.cond = {"m3": L["m3"], "m2": L["m2"], "m1": L["m1"], "poly2": L["poly2"], "poly": L["poly"],
                     "ndiff": ndiff, "pdiff": pdiff, "nwell": L["nwell"]}
        self.act = kdb.Region(self.top.begin_shapes_rec(self.ly.layer(GDS_NUM["act"], 0))).merged()
        self.names = self.name_nets()
        # per layer: {net name: merged region}
        circ = next(l2n.netlist().each_circuit_top_down())
        self.reg = {k: {} for k in self.cond}
        for net in circ.each_net():
            nm = self.names.get(net.cluster_id, net.expanded_name())
            for k, lay in self.cond.items():
                r = l2n.shapes_of_net(net, lay, True)
                if not r.is_empty():
                    self.reg[k][nm] = (self.reg[k][nm] + r).merged() if nm in self.reg[k] else r.merged()
        self.reg["diff"] = {}
        for k in ("ndiff", "pdiff"):
            for nm, r in self.reg[k].items():
                self.reg["diff"][nm] = (self.reg["diff"][nm] + r).merged() if nm in self.reg["diff"] else r
        self.all = {k: kdb.Region() for k in self.reg}
        for k, d in self.reg.items():
            for r in d.values():
                self.all[k] += r
            self.all[k].merge()
        self.gate = (self.all["poly"] & self.act).merged()
        self.strips = {}
        self.win, self.full = {}, {}          # a net cut to a window: its window and whole shapes

    def name_nets(self):
        """cluster id -> name, by probing the generator's metal rectangles."""
        blk, _ = gen.build()
        names, seen = {}, defaultdict(set)
        layer = {"metal1": "m1", "metal2": "m2", "metal3": "m3"}
        for net, lay, x0, y0, x1, y1 in blk.netrects:
            if lay not in layer:
                continue
            p = kdb.DPoint((x0 + x1) / 2 * gen.LAMBDA_UM, (y0 + y1) / 2 * gen.LAMBDA_UM)
            n = self.l2n.probe_net(self.L[layer[lay]], p)
            if n is None:
                sys.exit(f"no {lay} shape of {net} at {p}")
            seen[net].add(n.cluster_id)
            if names.setdefault(n.cluster_id, net) != net:
                sys.exit(f"short: {net} and {names[n.cluster_id]} are one net (at {p})")
        opens = {k: v for k, v in seen.items() if len(v) > 1}
        nodes = [k for k in opens if k.startswith(("ND", "NR", "PG")) or k in ("NG", "PCK")]
        if nodes:
            sys.exit(f"open: {nodes} drawn as several nets")
        return names

    def a(self, r):
        return r.area() * self.dbu * self.dbu

    def field_split(self, r):
        """[(net, region)] of a region over field: the N-well's net or the substrate (VSS)."""
        out = []
        for w, rw in self.reg["nwell"].items():
            part = r & rw
            if not part.is_empty():
                out.append((w, part))
        rest = r - self.all["nwell"]
        if not rest.is_empty():
            out.append(("VSS", rest))
        return out

    def strip(self, k, nm):
        """Outside strip of a net's edges on layer k (of its whole shape, cut to the net's window)."""
        if (k, nm) not in self.strips:
            r = self.full[nm][k] if nm in self.full else self.reg[k][nm]
            d = round(STRIP / self.dbu)
            s = (r.sized(d) - r).merged()
            self.strips[(k, nm)] = (s & self.win[nm]) if nm in self.win else s
        return self.strips[(k, nm)]

    def couplings(self, net):
        """{other net: {(upper, lower, kind): [area um2, edge um, fF]}} of a net, per the table."""
        out = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
        d = STRIP

        def add(other, key, area=0.0, edge=0.0):
            if other == net:
                return
            ca, cf = DOC[key[:2]] if key[:2] in DOC else (None, None)
            if ca is None:
                sys.exit(f"no table value for {key}")
            e = out[other][key]
            e[0] += area
            e[1] += edge
            e[2] += area * ca + edge * cf

        # 1) the net as the upper plate
        for k in STACK[:4]:                                # m3, m2, m1, poly2
            if net not in self.reg[k]:
                continue
            for mode, base in (("area", self.reg[k][net]), ("fringe", self.strip(k, net))):
                rest = base
                for low in STACK[STACK.index(k) + 1:]:
                    if rest.is_empty():
                        break
                    for other, ro in self.reg[low].items():
                        if not ro.bbox().overlaps(rest.bbox()):
                            continue
                        part = rest & ro
                        if part.is_empty():
                            continue
                        g = "poly" if k == "poly2" else GROUP[low]
                        key = (k, g, mode)
                        if mode == "area":
                            add(other, key, area=self.a(part))
                        else:
                            add(other, key, edge=self.a(part) / d)
                    rest = rest - self.all[low]
                for other, part in self.field_split(rest):
                    if k == "poly2":
                        sys.exit("POLY2 over field: no table value")
                    if mode == "area":
                        add(other, (k, "field", mode), area=self.a(part))
                    else:
                        add(other, (k, "field", mode), edge=self.a(part) / d)
        if net in self.reg["poly"]:
            r = self.reg["poly"][net]
            g = r & self.act
            for body, part in self.field_split(g):          # gate area to the body
                add(body, ("pgate" if body != "VSS" else "ngate", "chan", "area"), area=self.a(part))
            for other, part in self.field_split(r - self.act):
                add(other, ("poly", "field", "area"), area=self.a(part))
            s = self.strip("poly", net)
            for k in ("ndiff", "pdiff"):                     # gate fringe along source / drain
                for other, ro in self.reg[k].items():
                    part = s & ro
                    if not part.is_empty():
                        add(other, ("ngate" if k == "ndiff" else "pgate", "chan", "fringe"),
                            edge=self.a(part) / d)
            for other, part in self.field_split(s - self.act):
                add(other, ("poly", "field", "fringe"), edge=self.a(part) / d)
        for k in ("ndiff", "pdiff"):                           # junctions
            if net not in self.reg[k]:
                continue
            r = self.reg[k][net]
            j = (r - self.all["nwell"]) if k == "ndiff" else (r & self.all["nwell"])
            s = (self.strip(k, net) - self.gate)
            for body, part in self.field_split(j):
                add(body, (k, "field", "area"), area=self.a(part))
            for body, part in self.field_split(s - self.act):
                if (k == "ndiff") == (body == "VSS"):
                    add(body, (k, "field", "fringe"), edge=self.a(part) / d)
        # 2) the net as the lower plate under other nets' conductors (shielded by any layer between)
        for low in STACK[1:]:
            if net not in self.reg[low]:
                continue
            mine = self.reg[low][net]
            for up in STACK[:STACK.index(low)]:
                if up == "poly" and low == "diff":
                    continue                                   # the gate: counted from the poly side
                shield = kdb.Region()
                for mid in STACK[STACK.index(up) + 1:STACK.index(low)]:
                    shield += self.all[mid]
                base = (mine - shield) if not shield.is_empty() else mine
                if base.is_empty():
                    continue
                g = "poly" if up == "poly2" else GROUP[low]
                for other, ro in self.reg[up].items():
                    if other == net or not ro.bbox().overlaps(base.bbox()):
                        continue
                    part = base & ro
                    if not part.is_empty():
                        add(other, (up, g, "area"), area=self.a(part))
                    part = base & self.strip(up, other)
                    if not part.is_empty():
                        add(other, (up, g, "fringe"), edge=self.a(part) / d)
        # the gate fringe seen from a source / drain net: poly edges of other nets over this diffusion
        for k in ("ndiff", "pdiff"):
            if net not in self.reg[k]:
                continue
            mine = self.reg[k][net]
            for other, ro in self.reg["poly"].items():
                if other == net or not ro.bbox().enlarged(10).overlaps(mine.bbox()):
                    continue
                part = mine & self.strip("poly", other)
                if not part.is_empty():
                    add(other, ("ngate" if k == "ndiff" else "pgate", "chan", "fringe"), edge=self.a(part) / d)
        return out

    def facing(self, net):
        """{(layer, other net): facing length um} within FACE um on the same metal layer."""
        out = defaultdict(float)
        dist = round(FACE / self.dbu)
        for k in ("m1", "m2", "m3"):
            if net not in self.reg[k]:
                continue
            mine = self.reg[k][net]
            box = mine.bbox().enlarged(dist)
            for other, ro in self.reg[k].items():
                if other == net or not ro.bbox().overlaps(box):
                    continue
                pairs = mine.separation_check(ro, dist, False, kdb.Region.Projection)
                for ep in pairs.each():
                    out[(k, other)] += ep.first.length() * self.dbu
        return out


def clip(ex, win, net):
    """Restrict one net's own shapes to a window (um box); its edges stay those of the whole shape."""
    box = kdb.Region(kdb.Box(*(round(v / ex.dbu) for v in win)))
    ex.full[net] = {k: ex.reg[k][net] for k in ex.reg if net in ex.reg[k]}
    ex.win[net] = box
    for k, r in ex.full[net].items():
        part = (r & box).merged()
        if part.is_empty():
            del ex.reg[k][net]
        else:
            ex.reg[k][net] = part
    ex.strips = {kk: v for kk, v in ex.strips.items() if kk[1] != net}


def unclip(ex, net):
    for k in ex.reg:
        ex.reg[k].pop(net, None)
    for k, r in ex.full.pop(net).items():
        ex.reg[k][net] = r
    ex.win.pop(net)
    ex.strips = {kk: v for kk, v in ex.strips.items() if kk[1] != net}


def total(c, switching):
    held = sum(e[2] for o, ks in c.items() if o not in switching for e in ks.values())
    sw = {o: sum(e[2] for e in ks.values()) for o, ks in c.items() if o in switching}
    return held, sw


DRAWN = {1: ("poly2/poly/area", "poly2/poly/fringe", "PIP POLY2 over POLY1"),
         6: ("ndiff/field/area", "ndiff/field/fringe", "n+ junction"),
         7: ("ndiff/field/area", "ndiff/field/fringe", "n+ junction"),
         8: ("ngate/chan/area", "ngate/chan/fringe", "gate area / source-drain edge"),
         9: ("ngate/chan/area", "ngate/chan/fringe", "gate area / source-drain edge")}


def flat(c):
    return {o: {"/".join(k): [round(x, 4) for x in e] for k, e in ks.items()} for o, ks in c.items()}


def wiring(keys):
    """fF of the wiring terms (metal, field poly) of {key: [area, edge, fF]}: the terms that a netlist
    of the devices (junctions, gate and overlap capacitance in their models) does not already hold."""
    return sum(v[2] for k, v in keys.items() if k.split("/")[0] in ("m1", "m2", "m3") or k.startswith("poly/field"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=gen.DEFAULT_OUT / "cbcm_full.gds")
    args = ap.parse_args(argv)
    ex = Extract(args.gds)
    body = body_windows()
    rows, dump, geom = [], {}, {}
    print(f"{'cell':4s} {'structure':16s} {'body fF':>8s} {'lead fF':>8s} {'pair':>7s} {'dC fF':>8s} "
          f"{'ND-sw fF':>9s} {'NR-sw fF':>9s}  drawn")
    for i in range(gen.NCELL):
        nd, nr = f"ND{i}", f"NR{i}"
        sw = SWITCHING | {f"PG{i}", nd, nr}
        c_nd, c_nr = ex.couplings(nd), ex.couplings(nr)
        h_nd, s_nd = total(c_nd, sw)
        h_nr, s_nr = total(c_nr, sw)
        # body: the structure's window; pair: the band window (ND minus NR); lead: the rest of ND
        parts = {"body": 0.0}
        if i in body:
            clip(ex, body[i], nd)
            cb = ex.couplings(nd)
            parts["body"] = total(cb, sw)[0]
            unclip(ex, nd)
            dump[nd + "_body"] = flat(cb)
            if i in DRAWN:
                ka, ke, what = DRAWN[i]
                fa = flat(cb).get("VSS", {})
                geom[i] = {"what": what, "area_um2": fa.get(ka, [0, 0, 0])[0],
                           "edge_um": fa.get(ke, [0, 0, 0])[1]}
        clip(ex, band_window(i), nd)
        parts["band"] = total(ex.couplings(nd), sw)[0]
        unclip(ex, nd)
        clip(ex, band_window(i), nr)
        band_nr = total(ex.couplings(nr), sw)[0]
        unclip(ex, nr)
        lead = h_nd - parts["body"] - parts["band"]
        pair = parts["band"] - band_nr
        face = ex.facing(nd)
        lateral = round(sum(v for (k, o), v in face.items() if o not in sw), 1)
        g = geom.get(i)
        drawn = f"{g['what']}: {g['area_um2']:.2f} um2, {g['edge_um']:.2f} um" if g else ""
        rows.append(dict(cell=i, structure=gen.STRUCTURES[i], doc_body_fF=round(parts["body"], 2),
                         doc_lead_fF=round(lead, 2), doc_pair_fF=round(pair, 3), doc_dC_fF=round(h_nd - h_nr, 2),
                         nd_switching_fF=round(sum(s_nd.values()), 3), nr_switching_fF=round(sum(s_nr.values()), 3),
                         nd_facing_held_um=lateral, drawn=drawn))
        dump[nd], dump[nr] = flat(c_nd), flat(c_nr)
        dump[nd + "_facing_um"] = {f"{k}:{o}": round(v, 2) for (k, o), v in face.items()}
        dump[nr + "_facing_um"] = {f"{k}:{o}": round(v, 2) for (k, o), v in ex.facing(nr).items()}
        print(f"{i:4d} {gen.STRUCTURES[i]:16s} {parts['body']:8.2f} {lead:8.2f} {pair:+7.3f} {h_nd - h_nr:8.2f} "
              f"{sum(s_nd.values()):9.3f} {sum(s_nr.values()):9.3f}  {drawn}")
    # the nets that switch (the generator, PCK, NG, PG<i>): their couplings and wiring load
    loads = {}
    for n in sorted(set(ex.reg["m1"]) | set(ex.reg["m2"]) | set(ex.reg["m3"]) | set(ex.reg["poly"])):
        if n in SWITCHING or (n.startswith("PG") and n[2:].isdigit()):
            dump[n] = flat(ex.couplings(n))
            loads[n] = round(sum(wiring(ks) for ks in dump[n].values()), 3)
    print("wiring load of the switching nets (fF, metal and field poly; gates and junctions are in the "
          "device models): " + ", ".join(f"{k} {v:.1f}" for k, v in sorted(loads.items(), key=lambda t: -t[1])))
    out = gen.DEFAULT_OUT
    (out / "cbcm_c.json").write_text(json.dumps({"table": "rule document v1.1, 5.4 and 5.5 (typical)",
                                                 "cells": rows, "drawn": geom, "loads": loads,
                                                 "couplings": dump}, indent=1))
    with open(HERE / "cbcm_c.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out / 'cbcm_c.json'} and {HERE / 'cbcm_c.csv'}")
    return rows


if __name__ == "__main__":
    main()
