#!/usr/bin/env python3
"""Faults that chip_erc.py, gds_check.py, current_density.py and scripts/calibre_rules.py must each
catch, on copies of the chip GDS.

  ERC              the SDI route cut at its pad port (its gates float); ROW_SEL3's route cut between the
                   control block and the array (its gates keep only chip_lvs's anchor pin, which drives
                   nothing); the array's n+ well taps without contacts (PMOS bulks on wells no pad
                   reaches); the L-split gate bar joined to the D1 drain strip (a gate on a PAD force port)
  GDS              a vertex 5 nm off the grid; a shape on a layer the PDK map does not have; a shape on
                   NODRC; an edge at 30 degrees; a top-level label on MET2TXT; a metal1 square in the scribe
                   lane (the outer 60 um); one analog pad moved by 1 um (its bond pad no longer that of
                   MPW_PAD_28pin); a text 5 nm off the grid
  current density  the HT force line narrowed to 3 um for 10 um next to its pad port (7 mA: 2.3 mA/um);
                   14 of the 15 VIA1 cuts under the heater's head A removed (7 mA through one cut)
  Calibre-only     MOS-C's n+ well taps removed (2.ACT.T1: no tap within 60 um); the L-split NSD pulled
                   in by 0.3 um (5.NSD.E); the heater's LVSD shortened by 0.2 um (14.PL2PR.S2: its
                   contacts no longer abut the body)
  rules 7-12       (scripts/metal_rules.py, against the pad ring alone) the south VSS line back to its
                   full 9 um under the CBCM: with the CBCM's generator gnd rail on it the metal is 11.8 um,
                   wide, and the rail's fingers 0.9 um above it are too close (8.MET1.S2, 34 places; the
                   kit deck's shielded check never reports this rule)
Each fault must turn its check from clean to failing, naming the fault. ERC, the GDS checks and rules
7-12 pass as built; current density and the Calibre-only checks already report findings as built (the
1 mA/um assumption; the CBCM n+ junction cells), so their faults must add a finding of their own.

usage: python3 designs/etri050/chip/checks_selftest.py [--gds build/pdkv_Top.gds]    (about 8 min)
"""
import argparse
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

import chip_erc
import chip_lvs
import current_density
import gds_check

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
import calibre_rules  # noqa: E402


def cut_port(name):
    def f(ly):
        pin = {p[0]: p for p in chip_lvs.pad_pins()}[name]
        r = kdb.DBox(*pin[3]).to_itype(ly.dbu).enlarged(2000)          # the port and 2 um around it
        top = ly.top_cell()
        for n in (34, 35, 36):
            for s in list(top.shapes(ly.layer(n, 0)).each()):
                if s.bbox().overlaps(r):
                    s.delete()
    return f


def cut_row_sel3(ly):
    """Cut ROW_SEL3's metal1 route (x 810-812 um, y 1056-1058.2) between the control block and the array."""
    top = ly.top_cell()
    m1 = ly.layer(32, 0)
    cut = kdb.Region(kdb.DBox(810, 1056.0, 812, 1058.2).to_itype(ly.dbu))
    for s in list(top.shapes(m1).each()):
        if s.bbox().overlaps(cut.bbox()):
            rest = kdb.Region(s.polygon) - cut
            s.delete()
            top.shapes(m1).insert(rest)


def untie_array(ly):
    c = ly.cell("karray")
    c.flatten(-1, True)
    n_plus = kdb.Region(c.shapes(ly.layer(14, 0))) & kdb.Region(c.shapes(ly.layer(2, 0)))
    for s in list(c.shapes(ly.layer(31, 0)).each()):
        if not (kdb.Region(s.polygon) & n_plus).is_empty():
            s.delete()


def gate_to_d1(ly):
    ly.top_cell().shapes(ly.layer(32, 0)).insert(kdb.DBox(959.9, 1397.5, 964.8, 1398.5).to_itype(ly.dbu))


def off_grid(ly):
    ly.top_cell().shapes(ly.layer(32, 0)).insert(kdb.Box(600000, 600000, 601005, 601000))


def foreign(ly):
    ly.top_cell().shapes(ly.layer(99, 0)).insert(kdb.Box(600000, 600000, 601000, 601000))


def nodrc(ly):
    ly.top_cell().shapes(ly.layer(58, 0)).insert(kdb.Box(600000, 600000, 601000, 601000))


def skew(ly):
    """A metal1 triangle with a 30 degree edge (corners on the grid)."""
    ly.top_cell().shapes(ly.layer(32, 0)).insert(kdb.Polygon([kdb.Point(600000, 600000), kdb.Point(601730, 600000),
                                                             kdb.Point(600000, 601000)]))


def one_via(ly):
    """Keep one of the 15 VIA1 cuts that join HT's metal2 to heater head A's metal1 (x 1048-1070, y 1344-1366)."""
    top = ly.top_cell()
    v1 = ly.layer(33, 0)
    near = list(top.shapes(v1).each_overlapping(kdb.DBox(1048, 1344, 1070, 1366).to_itype(ly.dbu)))
    for s in near[1:]:
        s.delete()


def flat(ly, name):
    c = ly.cell(name)
    c.flatten(-1, True)
    return c


def untap_mosc(ly):
    """Remove MOS-C's n+ well taps (ACT under NSD in the mosc cell)."""
    c = flat(ly, "mosc")
    nplus = kdb.Region(c.shapes(ly.layer(14, 0)))
    for s in list(c.shapes(ly.layer(11, 0)).each()):
        if not (kdb.Region(s.polygon) & nplus).is_empty():
            s.delete()


def nsd_in(ly):
    """Pull the L-split's NSD in by 0.3 um."""
    c = flat(ly, "lsplit")
    li = ly.layer(14, 0)
    r = kdb.Region(c.shapes(li)).merged().sized(-300)
    c.shapes(li).clear()
    c.shapes(li).insert(r)


def lvsd_short(ly):
    """Shorten the heater's LVSD body by 0.2 um at each end (its contacts no longer abut it)."""
    c = flat(ly, "heater")
    li = ly.layer(60, 0)
    r = kdb.Region(c.shapes(li)).merged().sized(-200)
    c.shapes(li).clear()
    c.shapes(li).insert(r)


def label(ly):
    ly.top_cell().shapes(ly.layer(44, 0)).insert(kdb.Text("VDD", kdb.Trans(kdb.Point(600000, 600000))))


def in_lane(ly):
    """A metal1 square in the west scribe lane (x 30-40 um)."""
    ly.top_cell().shapes(ly.layer(32, 0)).insert(kdb.DBox(30, 900, 40, 910).to_itype(ly.dbu))


def move_pad(ly):
    """Move the pad ring's first analog pad (PANA) by 1 um."""
    ring = ly.cell("pdkv_Pad")
    inst = next(i for i in ring.each_inst() if i.cell.name == "PANA")
    inst.transform(kdb.Trans(kdb.Vector(1000, 0)))


def text_off_grid(ly):
    ly.top_cell().shapes(ly.layer(48, 0)).insert(kdb.Text("x", kdb.Trans(kdb.Point(600005, 600000))))


def narrow_ht(ly):
    """Cut the HT line's 9 um metal2 (y 1350-1359) to 3 um over x 1440-1450 (die um), next to E7."""
    top = ly.top_cell()
    m2 = ly.layer(34, 0)
    cut = kdb.Region(kdb.DBox(1440, 1353, 1450, 1359).to_itype(ly.dbu))
    for s in list(top.shapes(m2).each()):
        if s.bbox().overlaps(cut.bbox()):
            rest = kdb.Region(s.polygon) - cut
            s.delete()
            top.shapes(m2).insert(rest)


def wide_south(ly):
    """The south VSS line back to 9 um under the CBCM (y 446-448.5 over x 1144-1456 added)."""
    ly.top_cell().shapes(ly.layer(32, 0)).insert(kdb.DBox(1144, 446, 1456, 448.5).to_itype(ly.dbu))


def run(fn, gds):
    ly = kdb.Layout()
    ly.read(str(gds))
    fn(ly)
    out = Path(tempfile.mkdtemp()) / "pdkv_Top.gds"
    ly.write(str(out))
    return out


def erc(g):
    ok, out = chip_erc.erc(g)
    return ok, "\n".join(out)


def gds(g):
    ok, out = gds_check.check(g, gds_check.gpio_default(), gds_check.pads_default())
    return ok, "\n".join(out)


def density(g):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = current_density.main(["--gds", str(g)])
    return code == 0, buf.getvalue()


def calibre(g):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = calibre_rules.main(["--gds", str(g)])
    return code == 0, buf.getvalue()


def metal(g):
    """scripts/metal_rules.py (KLayout batch) with the pad ring alone as baseline: clean = nothing outside it."""
    env = dict(os.environ)
    env.setdefault("KLAYOUT_PATH", str(Path.home() / ".klayout"))
    r = subprocess.run(["klayout", "-b", "-r", str(HERE.parents[2] / "scripts/metal_rules.py"), "-rd", f"gds={g}",
                        "-rd", f"baseline={HERE / 'build/pdkv_Pad.gds'}"], capture_output=True, text=True, env=env)
    out = r.stdout + r.stderr
    return ", 0 not in the baseline" in out, out


TESTS = [("ERC: SDI cut at its port", cut_port("SDI"), erc, "float"),
         ("ERC: ROW_SEL3 cut (anchor pin only)", cut_row_sel3, erc, "row_sel3 (9 gates)"),
         ("ERC: array well taps without contacts", untie_array, erc, "not a padded N-well"),
         ("ERC: L-split gate joined to D1", gate_to_d1, erc, "unprotected port: D1"),
         ("GDS: vertex 5 nm off grid", off_grid, gds, "off grid: pdkv_Top layer 32"),
         ("GDS: layer 99", foreign, gds, "not in the layer map"),
         ("GDS: NODRC shape", nodrc, gds, "not a designer's layer: ['NODRC']"),
         ("GDS: 30 degree edge", skew, gds, "edges at other angles: pdkv_Top layer 32"),
         ("GDS: top-level MET2TXT label", label, gds, "VDD@MET2TXT"),
         ("GDS: metal1 in the scribe lane", in_lane, gds, "shapes in it: MET1 1 in (30,900;40,910)"),
         ("GDS: an analog pad moved by 1 um", move_pad, gds, "in MPW_PAD_28pin.gds, XOR 2 in"),
         ("GDS: a text 5 nm off grid", text_off_grid, gds, "text positions off it: pdkv_Top layer 48: 1"),
         ("current density: HT line 3 um", narrow_ht, density, "HT: m2 3.00 um"),
         ("current density: one VIA1 under heater head A", one_via, density, "HT: v1 x1, 7.00-7.00 mA per cut"),
         ("Calibre: MOS-C well taps removed", untap_mosc, calibre, "2.ACT.T1 worst distance from transistor diffusion to a tap of its well: over 60"),
         ("Calibre: L-split NSD pulled in", nsd_in, calibre, "5.NSD.E:"),
         ("Calibre: heater LVSD shortened", lvsd_short, calibre, "14.PL2PR.S2:"),
         ("rules 7-12: south VSS line 9 um under the CBCM (wide metal)", wide_south, metal, "8.MET1.S2: 34")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    a = ap.parse_args(argv)
    bad = 0
    for name, check in (("ERC", erc), ("GDS", gds), ("current density (known findings only)", density),
                        ("Calibre-only checks (known findings only)", calibre), ("rules 7-12", metal)):
        ok, text = check(a.gds)
        print(f"as built, {name}: {'clean' if ok else 'fails'}")
    for name, fault, check, sign in TESTS:
        ok, text = check(run(fault, a.gds))
        caught = not ok and sign in text
        bad += not caught
        print(f"{'caught' if caught else 'MISSED'}  {name}")
    print(f"checks selftest: {len(TESTS) - bad} of {len(TESTS)} faults caught")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
