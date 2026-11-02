#!/usr/bin/env python3
"""The checks of ETRI's Calibre DRC deck that the kit's KLayout deck leaves out (KLayout Python module).

ETRI checks a submitted GDS with its Calibre deck. The kit has that deck
(tech/Klayout_DRC_Script/Calibre_DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal, 164 rule checks) and the
summary of a Calibre run on a fabricated chip (pong_pt1, MPW2025 STD-II, Projects/RTL/pong_pt1/.../DRC_0).
The kit's KLayout deck (etri_05um_generated_final.drc) converts most checks but 74 Calibre checks have no
check of that name in it, and one converted check is empty: its 2.ACT.W2 measures NMOS.or(PMOS).not(POLY1)
where its NMOS and PMOS are the gate areas, so nothing is ever measured. scripts/metal_rules.py checks
rules 7-12 and scripts/antenna_rules.py the antenna rules (3.PL1.ANT among the 74) with the rule document's
values; metal_rules.py does not follow the Calibre definitions of the checks below.

This script translates 72 of the 74 and 2.ACT.W2 from the deck's SVRF (73 checks), with the deck's layer
derivations (PWELL is the drawn PWELL or the substrate outside every N-well, NTAP/PTAP are diffusion
without poly, NGATE/PGATE, the PNP collector ring, PRES_DEF, POLY1_CAP ...) and its macros:
  Width_check  INT  < v ABUT < 90 SINGULAR REGION   -> width_check
  OneSpace     EXT  < v ...                          -> space_check
  TwoSpace     EXT a b < v ...                       -> separation_check
  Enc_check    ENC a b < v ... OVERLAP               -> enclosing_check (b encloses a), plus the polygons of a
                                                        that cross b (OVERLAP; KLayout does not flag them)
  NotExist     NOT INTERACT a b                      -> not_interacting
Translation choices, where KLayout has no exact equivalent:
  SIZE a BY d INSIDE OF w STEP 0.3 (2.ACT.T1/T2): repeated 0.3 um growths, each cut back to w, with the
      corners cut as Calibre's TRUNCATE does (KLayout size mode 1). The worst distance (0.3 um steps)
      from a transistor's diffusion to a tap of its well is printed too.
  WITH WIDTH m >= 10 (wide metal of 9.VIA1.E2 ... 11.VIA2.E4): the parts that survive shrinking by
      4.99 um (as the KLayout deck defines MET1UP10).
  ENC of gate edges (2.ACT.E1): the 0.85 um strip beyond each gate side edge must be diffusion.
  INT of gate sides <= 100 (3.PL1.W2): gate by gate (one check over all sides would pair different gates).
  15.CAP.bad4: the LVSD strip of a PIP must share a whole edge of its POLY2 plate.
  19.IO.W1 (total ESD finger width, a DFM PROPERTY check) is not translated; it is reported as not checked
      when the layout has ESD (52) shapes, and has no input otherwise (our chip has none).

Pong_pt1's Calibre results are the reference: for these checks they have 9.VIA1.E2 4 and 9.VIA1.E4 4 and
nothing else. `--pong` runs this script on the kit's pong_pt1 GDS and compares the counts, and for the
nonzero checks the result boxes, with the Calibre results database.

The Calibre deck has no seal ring zone (its history notes that seal ring results of the contact and via
width checks are waived); markers that lie in the outer 30 um of CHIPBOUNDARY, as the KLayout deck takes
the zone, are counted apart. With --baseline <gds> (for the chip: the pad ring alone, whose ETRI GPIO
cells are not ours), markers at the same place in the baseline are counted apart too, as in
metal_rules.py; exit 1 when a marker is in neither.

usage: python3 scripts/calibre_rules.py --gds <file.gds> [--baseline <file.gds>] [--show 3]
       python3 scripts/calibre_rules.py --pong [<kit>]         (the kit from $ETRI050_DK by default)
"""
import argparse
import collections
import os
import re
import sys
import time
from pathlib import Path

import klayout.db as kdb

CAL = "tech/Klayout_DRC_Script/Calibre_DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal"
PONG = "Projects/RTL/pong_pt1/ETRI050_MyChip_MPW/pong_pt1_MPW2025_STD-II/chip_top/DRC_0"
PONG_CALIBRE = {"9.VIA1.E2": 4, "9.VIA1.E4": 4}      # its summary, for the checks of this script
NUM = dict(CHIPBOUNDARY=0, NWELLi=2, PWELLi=3, HNWELLi=4, HPWELLi=5, DWELLi=6, DNWELLi=7, DPWELLi=8, ACTi=11, POLY1i=12,
           POLY2i=13, NSDi=14, PSDi=15, NHRIi=20, CONTi=31, MET1i=32, VIA1i=33, MET2i=34, VIA2i=35, MET3i=36,
           PADi=37, RES=51, ESD=52, CAP=53, BJT=56, DIODE=57, NODRC=58, ESDD=59, LVSD=60)


class Layout:
    """The deck's original and derived layers of one GDS (all merged, in database units)."""

    def __init__(self, path):
        ly = kdb.Layout()
        ly.read(str(path))
        tops = ly.top_cells()
        if len(tops) != 1:
            raise SystemExit(f"{path}: {len(tops)} top cells")
        self.top = tops[0]
        self.dbu = ly.dbu
        self.path = Path(path)

        def layer(n):
            li = ly.find_layer(n, 0)
            return kdb.Region(self.top.begin_shapes_rec(li)).merged() if li is not None else kdb.Region()

        o = {k: layer(n) for k, n in NUM.items()}
        nodrc = o["NODRC"]
        g = {k: (v - nodrc if k.endswith("i") else v) for k, v in o.items()}
        self.L = L = {k[:-1] if k.endswith("i") else k: v for k, v in g.items()}
        everything = kdb.Region()
        for v in o.values():
            everything += v
        L["BULK"] = kdb.Region(everything.bbox()).sized(self.d(0.01))
        allnw = L["NWELL"] + L["HNWELL"] + L["DNWELL"]
        allpw = L["PWELL"] + L["HPWELL"] + L["DPWELL"]
        psub = L["BULK"] - allnw - allpw - L["DWELL"]
        L["PWELL"] = (L["PWELL"] + psub).merged() - nodrc
        A, P1, P2 = L["ACT"], L["POLY1"], L["POLY2"]
        L["EACT"] = A & L["ESD"]
        L["BACT"] = A & L["BJT"]
        L["NACT"] = A & L["NSD"]
        L["PACT"] = A & L["PSD"]
        L["NTAP"] = (L["NACT"] & L["NWELL"]).not_interacting(P1)
        L["PTAP"] = (L["PACT"] - L["NWELL"]).not_interacting(P1)
        L["GATE"] = A & P1
        L["NGATE"] = (L["NACT"] & P1) - L["NWELL"]
        L["PGATE"] = L["PACT"] & P1 & L["NWELL"]
        L["ALLGATE"] = (L["NGATE"] + L["PGATE"]).merged()
        L["NMOS"] = L["NACT"].interacting(P1)
        L["PMOS"] = L["PACT"].interacting(P1)
        L["POLY1_ON_ACT"] = P1.interacting(P1 & A)
        L["POLY1_FIELD"] = P1 - L["ALLGATE"]
        L["ACT_ON_CONT"] = L["CONT"].interacting(A)
        L["POLY1_ON_CONT"] = L["CONT"].interacting(P1)
        L["POLY2_ON_CONT"] = L["CONT"].interacting(P2)
        L["POLY2_ON_CONT_RES"] = L["POLY2_ON_CONT"].interacting(L["RES"])
        L["PL2_ONLY"] = P2.not_interacting(P1)
        L["CONT_ON_PL2_ONLY"] = L["CONT"].interacting(L["PL2_ONLY"])
        L["POLY1_CAP"] = P1.interacting(L["CAP"])
        L["POLY2_CAP"] = P2.interacting(L["CAP"])
        L["PL2_CAP_LVSD"] = L["LVSD"] & L["POLY2_CAP"]
        L["PPRES"] = P2 & L["LVSD"] & L["RES"]
        L["POLY2_RES"] = P2.interacting(L["PPRES"])
        L["PRES_DEF"] = L["LVSD"].inside(L["RES"])
        L["NWDIO_WELL"] = L["DIODE"] & L["NWELL"]
        L["NWDIO_NCAT"] = L["NWDIO_WELL"] & L["NACT"]
        L["NWDIO_PANO"] = L["NWDIO_WELL"] & L["PACT"]
        L["PWDIO_WELL"] = L["DIODE"] & L["PWELL"]
        L["PWDIO_PCAT"] = L["PWDIO_WELL"] & L["PACT"]
        L["PWDIO_NANO"] = L["PWDIO_WELL"] & L["NACT"]
        L["DIODE_ACT"] = A.interacting(L["DIODE"])
        L["DIODE_PSD"] = L["PSD"].interacting(L["DIODE"])
        L["DIODE_NSD"] = L["NSD"].interacting(L["DIODE"])
        pnp_well = L["BJT"] & L["NWELL"]
        pbact, nbact = L["BACT"] & L["PSD"], L["BACT"] & L["NSD"]
        L["PNP_E"] = pnp_well & pbact
        L["PNP_B"] = (pnp_well & nbact).inside(pnp_well.interacting(L["PNP_E"]))
        ring = pbact - pnp_well
        L["PNP_C"] = ring.with_holes(1, None).interacting(ring.holes().interacting(L["PNP_E"]))
        npn_well = L["BJT"] & L["PWELL"]
        L["NPN_E"] = npn_well & nbact
        L["NPN_B"] = (npn_well & pbact).inside(npn_well.interacting(L["NPN_E"]))
        ring = nbact - npn_well
        L["NPN_C"] = ring.with_holes(1, None).interacting((L["NACT"] - npn_well).holes().interacting(L["NPN_E"]))
        L["ESD_PL1"] = P1 & L["ESD"]
        L["ESD_GATE"] = L["ALLGATE"] & L["ESD"]
        L["ESD_ACT"] = A & L["ESD"]
        L["PEACT"] = L["EACT"] & L["PSD"]
        L["NEACT"] = L["EACT"] & L["NSD"]
        L["ESD_S"] = L["ESD_ACT"].interacting(L["ESD_GATE"]) - L["ESDD"]
        L["ESD_D"] = L["ESD_ACT"].interacting(L["ESD_GATE"]) & L["ESDD"]
        for m in ("MET1", "MET2", "MET3"):
            L[m + "UP10"] = L[m].sized(-self.d(4.99)).sized(self.d(4.99)) & L[m]

    def d(self, um):
        return int(round(um / self.dbu))


# ---- the macros ----------------------------------------------------------------------------------------
def width(lo, a, v):
    return a.width_check(lo.d(v))


def space(lo, a, v):
    return a.space_check(lo.d(v))


def sep(lo, a, b, v):
    return a.separation_check(b, lo.d(v))


def enc(lo, inner, outer, v):
    """ENC inner outer < v ... OVERLAP: too little enclosure, and inner polygons crossing outer's edge.
    outer is first cut to v + 0.05 um around inner (the cut edges are too far to be measured): the merged
    power grid makes the check several times slower otherwise."""
    d = lo.d(v)
    near = outer & inner.sized(d + lo.d(0.05))
    return [near.enclosing_check(inner, d), inner.interacting(inner - outer).overlapping(outer)]


def coincident(a, b):
    """COIN EDGE a b: the parts of a's edges that lie on b's edges."""
    return a.edges() & b.edges()


def tap_distance(lo, sd, taps, well):
    """2.ACT.T1/T2 (SIZE taps BY 2.0, then 29.0, then 29.0 INSIDE OF well STEP 0.3; sd NOT that): the
    diffusion of sd that taps grown 0.3 um at a time inside well do not reach in 60 um, and the distance
    at which the last of sd is reached (None when some is not)."""
    a = taps & well
    rest = sd - a
    done, worst = 0.0, (0.0 if rest.is_empty() else None)
    for total in (2.0, 29.0, 29.0):
        left = total
        while left > 1e-9:
            s = min(0.3, left)
            a = a.sized(lo.d(s), 1) & well
            left -= s
            done += s
            if worst is None:
                rest -= a
                if rest.is_empty():
                    worst = done
    return sd - a, worst


# ---- the checks ----------------------------------------------------------------------------------------
def long_gates(lo, gates, sides):
    """3.PL1.W2 (B = INT (POLY1 INSIDE EDGE ACT) <= 100 REGION; NOT ALLGATE B): the gates whose two sides
    on POLY1 edges are more than 100 um apart. Checked gate by gate (one width check over all side edges
    would pair the sides of different gates); a gate whose box is at most 100 um both ways is short."""
    out = kdb.Region()
    lim = lo.d(100)
    for p in gates.each():
        b = p.bbox()
        if b.width() <= lim and b.height() <= lim:
            continue
        g = kdb.Region(p)
        side = sides & g.edges()
        out += g - side.width_check(lim + 1).polygons()
    return [out]


def checks(lo, times=None):
    """{rule: [markers (EdgePairs, Region or Edges)]}, and notes; times = {} collects seconds per check."""
    L = lo.L
    r, notes = {}, {}
    A, P1, P2, CONT = L["ACT"], L["POLY1"], L["POLY2"], L["CONT"]

    def put(name, fn):
        t = time.time()
        r[name] = fn()
        if times is not None:
            times[name] = time.time() - t

    put("1.NWL.bad2", lambda: [L["NWELL"] & ((L["PACT"].not_interacting(P1) - L["BJT"]) - L["DIODE"])])
    put("1.PWL.bad1", lambda: [((L["PWELL"] - L["BJT"].not_interacting(L["PNP_E"])) - L["DIODE"])
                               .not_interacting(L["PTAP"].interacting(CONT))])
    put("1.PWL.bad2", lambda: [((L["PWELL"] - L["BJT"]) - L["DIODE"]) & L["NACT"].not_interacting(P1)])

    # 2.ACT.E1: ENC PGATE_W ACT < 0.85, PGATE_W = PGATE COINCIDENT EDGE POLY1 (the gate's side edges)
    put("2.ACT.E1", lambda: [(coincident(L["PGATE"], P1) + coincident(L["NGATE"], P1)).extended_out(lo.d(0.85)) - A])
    put("2.ACT.E4", lambda: enc(lo, L["NMOS"], L["PWELL"], 1.4))
    put("2.ACT.E5", lambda: enc(lo, L["PTAP"], L["PWELL"], 0.5))
    tap = {}
    put("2.ACT.T1", lambda: [tap.setdefault("2.ACT.T1", tap_distance(
        lo, L["PACT"].interacting(L["PGATE"]) & L["NWELL"], (L["NACT"] - L["PWELL"]).not_interacting(L["PWELL"]),
        L["NWELL"]))[0]])
    put("2.ACT.T2", lambda: [tap.setdefault("2.ACT.T2", tap_distance(
        lo, L["NACT"].interacting(L["ALLGATE"]) & L["PWELL"], (L["PACT"] - L["NWELL"]).not_interacting(L["NWELL"]),
        L["PWELL"]))[0]])
    notes.update({k: v[1] for k, v in tap.items()})
    put("2.ACT.W1", lambda: [width(lo, L["NMOS"], 1.6), width(lo, L["PMOS"], 1.6)])
    # 2.ACT.W2 (Calibre form): LENGTH (PN_ACT NOT GATE) > 100, PN_ACT = transistor diffusion
    pn = (L["NACT"] + L["PACT"]).merged()
    put("2.ACT.W2", lambda: [((pn.interacting(L["ALLGATE"]) & pn) - L["GATE"]).edges().with_length(lo.d(100) + 1, None, False)])

    # 3.PL1.O: INT (POLY1_ON_ACT NOT ACT) < 0.5, and gate poly edges on an ACT edge
    put("3.PL1.O", lambda: [width(lo, L["POLY1_ON_ACT"] - A, 0.5), coincident(L["POLY1_ON_ACT"], A)])
    put("3.PL1.S2", lambda: [space(lo, L["NGATE"], 0.6), space(lo, L["PGATE"], 0.6)])
    put("3.PL1.S3", lambda: [sep(lo, A, P1, 0.5)])
    p1tr = P1.interacting(A)
    put("3.PL1.S4", lambda: [sep(lo, p1tr, A.interacting(p1tr), 0.5)])
    put("3.PL1.W2", lambda: long_gates(lo, L["ALLGATE"], P1.edges().inside_part(A)))
    put("4.PL2.bad2", lambda: [(P1 & P2) - L["CAP"]])

    for imp in ("NSD", "PSD"):
        n = "5" if imp == "NSD" else "6"
        put(f"{n}.{imp}.E", lambda imp=imp: [A.interacting(L[imp]) & L[imp].edges().extended_in(lo.d(0.5))])
        put(f"{n}.{imp}.bad1", lambda imp=imp: [L[imp].not_interacting(
            (((P1 & P2) & L[imp]) & L["CAP"]) + ((P2 & L[imp]) & L["RES"]) + A)])
    put("6.PSD.O", lambda: [L["PSD"] & L["NSD"]])

    put("7.CONT.E1", lambda: enc(lo, CONT, A, 0.5))
    put("7.CONT.E2", lambda: enc(lo, CONT, P1, 0.5))
    put("7.CONT.E3", lambda: enc(lo, CONT, L["MET1"], 0.6))
    put("7.CONT.E4", lambda: enc(lo, CONT.not_interacting(P2 & P1), P2 - L["RES"], 0.5))
    put("7.CONT.S3", lambda: [sep(lo, L["NGATE"], L["ACT_ON_CONT"], 0.75), sep(lo, L["PGATE"], L["ACT_ON_CONT"], 0.75)])
    put("7.CONT.S4", lambda: [sep(lo, L["POLY1_FIELD"], L["ACT_ON_CONT"], 0.75)])
    put("7.CONT.S6", lambda: [sep(lo, P2, L["ACT_ON_CONT"], 1.0)])
    put("7.CONT.S7", lambda: [sep(lo, L["POLY1_ON_CONT"], L["POLY2_RES"], 1.25)])
    put("7.CONT.S8", lambda: [sep(lo, L["CONT_ON_PL2_ONLY"], P1, 1.25)])
    put("7.CONT.bad2", lambda: [CONT.not_interacting(A + P1 + P2)])

    for via, low, up, cut, n in (("VIA1", "MET1", "MET2", "CONT", "9"), ("VIA2", "MET2", "MET3", "VIA1", "11")):
        v = L[via]
        put(f"{n}.{via}.E2", lambda v=v, low=low: enc(lo, v, L[low + "UP10"], 0.6))
        put(f"{n}.{via}.E4", lambda v=v, up=up: enc(lo, v, L[up + "UP10"], 0.6))
        put(f"{n}.{via}.S", lambda v=v, cut=cut: [sep(lo, v, L[cut], 0.6), v & L[cut]])
        put(f"{n}.{via}.S2", lambda v=v: [space(lo, v & v.sized(lo.d(0.8)).sized(-lo.d(2.4)).sized(lo.d(2.4)), 0.8)])

    put("13.PAD.E", lambda: sum((enc(lo, L["PAD"], L[m], 2.5) for m in ("MET1", "MET2", "MET3")), []))
    put("13.PAD.P", lambda: [L["PAD"].interacting(L["PAD"].sized(lo.d(19.99)).sized(-lo.d(19.99)) - L["PAD"])])

    # 14.PL2PR.S2: a resistor contact must not overlap its LVSD body and must share an edge with it
    body = L["LVSD"].interacting(L["PRES_DEF"])
    rc = L["POLY2_ON_CONT_RES"]
    put("14.PL2PR.S2", lambda: [rc & body, rc.not_interacting(coincident(rc, body))])

    cap1, cap2 = L["POLY1_CAP"], L["POLY2_CAP"]
    put("15.CAP.E1", lambda: enc(lo, CONT, cap1, 1.0))
    put("15.CAP.E2", lambda: enc(lo, CONT, cap2, 1.0))
    put("15.CAP.S1", lambda: [sep(lo, cap2, L["POLY1_ON_CONT"] & L["CAP"], 1.0)])
    put("15.CAP.S2", lambda: [sep(lo, cap2, L["POLY2_RES"], 2.0)])
    put("15.CAP.S3", lambda: [sep(lo, cap2, P2 - (L["RES"] + L["CAP"]), 2.0)])
    put("15.CAP.S4", lambda: [sep(lo, cap1, (P1 - L["CAP"]) - L["ESD"], 1.0)])
    put("15.CAP.S5", lambda: [space(lo, cap1, 1.0)])
    put("15.CAP.bad2", lambda: [cap2.not_interacting(cap1), cap1.not_interacting(cap2)])
    lv = L["PL2_CAP_LVSD"]
    put("15.CAP.bad3", lambda: [lv.sized(-lo.d(0.1)).sized(lo.d(0.1)), width(lo, lv, 0.2)])
    strip = L["LVSD"].interacting(lv)
    plate = set(cap2.edges().each())
    whole = kdb.Edges([e for e in coincident(cap2, strip).each() if e in plate])
    put("15.CAP.bad4", lambda: [strip.not_interacting(whole)])
    put("15.CAP.bad5", lambda: [strip - cap2])

    for kind in ("PNP", "NPN"):
        n = "16" if kind == "PNP" else "17"
        cb = (L[kind + "_C"] + L[kind + "_B"]).merged()
        put(f"{n}.{kind}.W2", lambda cb=cb: [width(lo, cb, 2.0), cb.sized(-lo.d(1.0) - 1).sized(lo.d(1.0) + 1)])

    esd = L["ESD"]
    put("19.IO.E1", lambda: enc(lo, L["ACT_ON_CONT"].inside(L["EACT"].interacting(P1)), L["EACT"], 1.0))
    put("19.IO.E2", lambda: enc(lo, L["ESD_ACT"], L["NSD"], 1.0) + enc(lo, L["ESD_ACT"], L["PSD"], 1.0))
    put("19.IO.S1", lambda: [sep(lo, L["ESD_GATE"], CONT & L["ESD_D"], 4.0)])
    put("19.IO.S2", lambda: [sep(lo, CONT & L["ESD_S"], L["ESD_GATE"], 1.0)])
    put("19.IO.S3", lambda: [space(lo, CONT & esd, 0.8)])
    sd = (L["PEACT"] + L["NEACT"]).merged() - P1
    put("19.IO.W2", lambda: [sd.not_interacting(sd.edges().with_length(lo.d(60), None, False))])
    put("19.IO.W3", lambda: [width(lo, L["POLY1_ON_ACT"] & esd, 0.7)])
    put("19.IO.W4", lambda: [width(lo, L["MET1"].interacting(CONT & L["ESD_D"]), 6.0)])
    notes["19.IO.W1"] = "not translated (DFM PROPERTY)" + ("; the layout has ESD shapes" if not esd.is_empty()
                                                         else "; no ESD (52) shapes, no input")

    nw_d = L["NWELL"] & L["DIODE"]
    grown = L["NWDIO_NCAT"].sized(lo.d(2.0))
    put("22.PNW.E1", lambda: [(grown + grown.holes()).merged().edges() - nw_d.edges()])
    put("22.PNW.E2", lambda: [(L["DIODE_ACT"] & L["NWELL"]).sized(lo.d(1.0)).edges()
                              - (L["DIODE_PSD"] + L["DIODE_NSD"]).edges()])
    put("22.PNW.S", lambda: [diode_space(lo, L["NWDIO_PANO"], L["NWDIO_NCAT"])])
    put("22.PNW.W1", lambda: [diode_length(lo, L["NWDIO_PANO"])])
    put("22.PNW.W2", lambda: [width(lo, L["NWDIO_NCAT"], 2.0),
                              L["NWDIO_NCAT"].sized(-lo.d(1.0) - 1).sized(lo.d(1.0) + 1)])
    put("22.PNW.bad1", lambda: [L["NWELL"].interacting(L["DIODE"]).edges() - L["DIODE"].edges()])
    put("23.NPW.E", lambda: [(L["DIODE_ACT"] - L["NWELL"]).sized(lo.d(1.0)).edges()
                             - (L["DIODE_PSD"] + L["DIODE_NSD"]).edges()])
    put("23.NPW.S", lambda: [diode_space(lo, L["PWDIO_NANO"], L["PWDIO_PCAT"])])
    put("23.NPW.W1", lambda: [diode_length(lo, L["PWDIO_NANO"])])
    put("23.NPW.W2", lambda: [width(lo, L["PWDIO_PCAT"], 2.0),
                              L["PWDIO_PCAT"].sized(-lo.d(1.0) - 1).sized(lo.d(1.0) + 1)])
    return r, notes


def diode_space(lo, ano, cat):
    """EXT [ano] cat == 4.5 OPPOSITE; ano NOT COIN INSIDE EDGE that: anode edges not 4.5 um from the cathode."""
    pairs = ano.separation_check(cat, lo.d(4.5) + 1, False, kdb.Metrics.Projection)
    at = kdb.Edges([p.first for p in pairs.each() if abs(p.distance() - lo.d(4.5)) <= 1])
    return ano.edges() - at


def diode_length(lo, a):
    """A diode diffusion edge shorter than 2 um or longer than 20 um."""
    e = a.edges()
    return e.with_length(None, lo.d(2.0), False) + e.with_length(lo.d(20.0) + 1, None, False)


def seal_zone(lo):
    """The seal ring zone, the outer 30 um of CHIPBOUNDARY (and the 0.01 um the deck's BULK adds around
    the layout), as the kit's KLayout deck takes it; empty without a chip boundary."""
    cb = lo.L["CHIPBOUNDARY"]
    if cb.is_empty():
        return cb
    return (cb - cb.sized(-lo.d(30.0))).sized(lo.d(0.02))


def marker_region(x):
    """A marker (polygon, edge pair or edge) as a region."""
    if isinstance(x, kdb.EdgePair):
        return kdb.Region(x.polygon(1))
    if isinstance(x, kdb.Edge):
        return kdb.Region(kdb.Box(x.bbox()).enlarged(1, 1))
    return kdb.Region(x)


def boxes(lo, markers, zone):
    """[(marker box in um, whether it lies in the seal ring zone)]."""
    out = []
    for m in markers:
        for x in m.each():
            out.append((str(x.bbox().to_dtype(lo.dbu)), not zone.is_empty() and (marker_region(x) - zone).is_empty()))
    return out


def run(path, times=False):
    t = time.time()
    lo = Layout(path)
    spent = {"layers": time.time() - t}
    r, notes = checks(lo, spent)
    if times:
        print("  slowest:", ", ".join(f"{k} {v:.1f} s" for k, v in sorted(spent.items(), key=lambda x: -x[1])[:6]))
    zone = seal_zone(lo)
    return lo, {k: boxes(lo, v, zone) for k, v in r.items()}, notes


def report(path, baseline=None, show=3, times=False):
    """Markers per check: in the seal ring zone (the 4.21 figure's ring: the Calibre deck has no zone
    and ETRI waives seal ring results), in the baseline, and the rest, which count."""
    t = time.time()
    lo, found, notes = run(path, times)
    base = run(baseline, times)[1] if baseline else {}
    total = seal = new = 0
    lines = []
    for rule in sorted(found, key=lambda k: [int(x) if x.isdigit() else x for x in k.replace(".", " ").split()]):
        b = found[rule]
        if not b:
            continue
        old = {x for x, z in base.get(rule, [])}
        ring = [x for x, z in b if z]
        fresh = [x for x, z in b if not z and x not in old]
        total += len(b)
        seal += len(ring)
        new += len(fresh)
        note = ", ".join(f"{k} {w}" for k, w in (("in the seal ring zone", len(ring)),
                                                 ("also in the baseline", len(b) - len(ring) - len(fresh))) if w)
        lines.append(f"  {rule}: {len(b)}" + (f" ({note})" if note else "")
                     + (f"   e.g. {'; '.join(fresh[:show])}" if fresh else ""))
    for k in ("2.ACT.T1", "2.ACT.T2"):
        w = notes[k]
        lines.append(f"  {k} worst distance from transistor diffusion to a tap of its well: "
                     + (f"{w:.1f} um (limit 60)" if w is not None else "over 60 um (see the markers)"))
    lines.append(f"  19.IO.W1: {notes['19.IO.W1']}")
    print("\n".join(lines))
    print(f"{lo.path.name}: {total} markers in {len(found)} Calibre-only checks, {seal} in the seal ring zone, "
          f"{new} {'not in the baseline' if baseline else 'elsewhere'} ({time.time() - t:.0f} s)")
    return total, new, found, notes


def pong(kit, times=False):
    gds = Path(kit) / PONG / "pong_pt1_Top_Pad.gds.gz"
    lo, found, notes = run(gds, times)
    calibre = calibre_results(Path(kit) / PONG / "pong_pt1_Pad.drc.results")
    bad = 0
    for rule, b in sorted(found.items()):
        want = PONG_CALIBRE.get(rule, 0)
        mine = sorted(x for x, z in b)
        if len(b) != want or (want and mine != calibre.get(rule)):
            bad += 1
            print(f"  {rule}: {len(b)}, Calibre {want}   e.g. {'; '.join(mine[:3])}"
                  + (f" / Calibre {'; '.join(calibre.get(rule, [])[:3])}" if want else ""))
    print(f"pong_pt1 (Calibre run of a fabricated chip): {len(found) - bad} of {len(found)} checks give "
          f"Calibre's count, the nonzero ones at Calibre's places" + ("" if not bad else f", {bad} differ"))
    for k in ("2.ACT.T1", "2.ACT.T2"):
        print(f"  {k} worst distance from transistor diffusion to a tap of its well: "
              + (f"{notes[k]:.1f} um" if notes[k] is not None else "over 60 um"))
    return bad


def calibre_results(path):
    """{check: [result box in um]} from a Calibre ASCII results database (polygons 'p n k' + k vertices)."""
    out = collections.defaultdict(list)
    lines = Path(path).read_text().split("\n")
    rule, i = None, 1
    while i < len(lines):
        t = lines[i].split()
        if len(t) == 1 and re.match(r"^\d+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$", t[0]):
            rule = t[0]
        elif t and t[0] == "p" and len(t) == 3 and rule:
            k, pts = int(t[2]), []
            while len(pts) < k:                            # vertices, after the cell name line (CN ...)
                i += 1
                v = lines[i].split()
                if len(v) == 2 and all(re.match(r"^-?\d+$", x) for x in v):
                    pts.append((int(v[0]), int(v[1])))
            xs, ys = [p[0] / 1000 for p in pts], [p[1] / 1000 for p in pts]
            out[rule].append(str(kdb.DBox(min(xs), min(ys), max(xs), max(ys))))
        i += 1
    return {k: sorted(v) for k, v in out.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--pong", nargs="?", const=os.environ.get("ETRI050_DK", ""))
    ap.add_argument("--times", action="store_true", help="print the slowest checks")
    a = ap.parse_args(argv)
    if a.pong is not None:
        if not a.pong:
            raise SystemExit("--pong needs the kit (or ETRI050_DK)")
        return 1 if pong(a.pong, a.times) else 0
    if not a.gds:
        ap.error("--gds or --pong")
    total, new, found, notes = report(a.gds, a.baseline, a.show, a.times)
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
