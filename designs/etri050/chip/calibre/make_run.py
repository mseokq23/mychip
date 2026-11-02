#!/usr/bin/env python3
"""A Calibre run folder for pdkv: ETRI's own Calibre decks, our GDS, the run settings ETRI used, the core's
LVS inputs and what our checks predict, to copy to a machine with Calibre; compare.py reads the results
back (there or here).

ETRI checks a submitted GDS with Calibre: the kit has the summary and results of its DRC run on pong_pt1
(MPW2025 STD-II, a fabricated chip; Calibre v2019.4, at most 1000 results per check and 4096 vertices per
result, results in cell space, summary by cell). The decks come from the kit's copy of the PDK
(docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz: Calibre/DRC, ANT, LVS) into the folder only,
not into the repository.

build/calibre/ (and build/pdkv_calibre.tar.gz of it):
  NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_{DRC,ANT,LVS}.cal   ETRI's decks, unchanged
  pong_pt1_Top_Pad.gds, pong_pt1_Pad.drc.summary.etri    the chip ETRI checked, and ETRI's summary of it
  pdkv_Top.gds                    the chip (build/pdkv_Top.gds; as submitted: no seal ring, no chip boundary)
  pdkv_Top_noseal.gds             only from a chip built with PDKV_SEAL=1: the same without its seal ring and
                                  chip boundary, as the default build makes it
  pdkv_Core.gds, pdkv_Core.cdl    the core's LVS inputs (lvs_inputs.py)
  drc_pong.cal                    1. pong_pt1 with ETRI's settings: the counts must be ETRI's (setup check)
  drc_pdkv_Top.cal (, drc_pdkv_Top_noseal.cal)   2. our chip, the same settings
  ant_pdkv_Top.cal                3. the antenna deck (the PDK's runant.com hands the deck to Calibre
                                     without a header, but the deck's LAYOUT lines are comments)
  lvs_pdkv_Core.cal               4. LVS of the core (the PDK's lvs_header.cal, our files, VDD/VSS by name)
  run_calibre.sh                  runs 1-4 as the design guide does (calibre -drc -hier / -lvs -hier)
  compare.py, expected.json       sorts the results: ETRI's pad cells, the seal ring if there is one (the
                                  deck waives its contact and via widths), known (CBCM n+ cells, 1.PWL.bad2),
                                  unexpected

usage: python3 designs/etri050/chip/calibre/make_run.py [--gds build/pdkv_Top.gds] [--out build/calibre]
       (the kit from $ETRI050_DK, <repo>/.pdk/ETRI050_DesignKit or ~/ETRI050_DesignKit, as run_chip.sh)
"""
import argparse
import gzip
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
CHIP = HERE.parent
REPO = CHIP.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE))
import calibre_rules  # noqa: E402
import lvs_inputs  # noqa: E402

PDK_TGZ = "docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz"
DECK = {k: f"NSPL_05CMOS_PDK_260820/Calibre/{k}/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_{k}.cal"
        for k in ("DRC", "ANT", "LVS")}
PONG = "Projects/RTL/pong_pt1/ETRI050_MyChip_MPW/pong_pt1_MPW2025_STD-II/chip_top/DRC_0"
RING = 30.0                     # seal ring width (assemble.py, rule document 4.21)
SEAL_RULES = ["7.CONT.W", "9.VIA1.W", "11.VIA2.W", "2.ACT.E5", "6.PSD.E"]

DRC_HEADER = """// {what}
// ETRI's settings for the pong_pt1 run whose summary the kit has: at most 1000 results per check, 4096
// vertices per result, results in cell space with the placement, summary by cell
LAYOUT PATH "{gds}"
LAYOUT PRIMARY "{top}"
LAYOUT SYSTEM GDSII
DRC RESULTS DATABASE "{out}.drc.results" ASCII
DRC MAXIMUM RESULTS 1000
DRC MAXIMUM VERTEX 4096
DRC CELL NAME YES CELL SPACE XFORM
DRC SUMMARY REPORT "{out}.drc.summary" REPLACE HIER
INCLUDE "NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal"
"""

ANT_HEADER = """// pdkv_Top: ETRI's antenna deck (the PDK's ant_header.cal with our file names)
LAYOUT PATH "pdkv_Top.gds"
LAYOUT PRIMARY "pdkv_Top"
LAYOUT SYSTEM GDSII
DRC RESULTS DATABASE "pdkv_Top.ant.results" ASCII
DRC MAXIMUM RESULTS ALL
DRC SUMMARY REPORT "pdkv_Top.ant.summary" REPLACE HIER
INCLUDE "NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal"
"""

LVS_HEADER = """// pdkv_Core: the chip core against its circuit (the PDK's lvs_header.cal with our file names)
LAYOUT PRIMARY "pdkv_Core"
LAYOUT PATH "pdkv_Core.gds"
LAYOUT SYSTEM GDSII

SOURCE PRIMARY "pdkv_Core"
SOURCE PATH "pdkv_Core.cdl"
SOURCE SYSTEM SPICE

LVS REPORT "pdkv_Core.lvs.rep"
LVS REPORT MAXIMUM 1000
LVS REPORT OPTION A B C D S V

ERC RESULTS DATABASE "pdkv_Core.erc.results" ASCII
ERC SUMMARY REPORT "pdkv_Core.erc.summary"
ERC MAXIMUM RESULTS 100

// The core's VDD comes in at two pads (W1: control block, array, RO; S7: CBCM) whose cells the pad ring's
// VDD rail joins; without the ring they are two nets with the label VDD, joined here by name.
VIRTUAL CONNECT NAME "VDD"

INCLUDE "NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_LVS.cal"
"""

RUN = """#!/bin/bash
# Run on a machine with Calibre (calibre on PATH, license set), from this folder. Takes a few minutes.
# Extra options for every run, e.g. CALIBRE_OPTS="-turbo 4", go through $CALIBRE_OPTS.
cd "$(dirname "$0")" || exit 1
OPTS=${{CALIBRE_OPTS:-}}
run() {{ echo "== $1"; shift; "$@" > "$LOG" 2>&1; echo "   exit $? (log: $LOG)"; }}
LOG=pong.drc.log         run "1. pong_pt1 with ETRI's settings (setup check)" calibre -drc -hier $OPTS drc_pong.cal
LOG=pdkv_Top.drc.log     run "2a. pdkv_Top DRC"                    calibre -drc -hier $OPTS drc_pdkv_Top.cal
{noseal}LOG=pdkv_Top.ant.log     run "3. pdkv_Top antenna"                 calibre -drc -hier $OPTS ant_pdkv_Top.cal
LOG=pdkv_Core.lvs.log    run "4. pdkv_Core LVS"                    calibre -lvs -hier $OPTS lvs_pdkv_Core.cal
if command -v python3 > /dev/null; then python3 compare.py .; else echo "no python3 here: run compare.py on these files elsewhere"; fi
"""
NOSEAL_LINE = 'LOG=pdkv_Top_noseal.drc.log run "2b. pdkv_Top without seal ring"     calibre -drc -hier $OPTS drc_pdkv_Top_noseal.cal\n'


def kit_dir():
    for k in (os.environ.get("ETRI050_DK"), REPO / ".pdk/ETRI050_DesignKit", Path.home() / "ETRI050_DesignKit"):
        if k and (Path(k) / PDK_TGZ).is_file():
            return Path(k)
    raise SystemExit(f"no kit with {PDK_TGZ} (set ETRI050_DK)")


def decks(kit, out):
    with tarfile.open(kit / PDK_TGZ) as tf:
        for k, member in DECK.items():
            f = tf.extractfile(member)                       # read the member itself: no paths from the archive
            (out / Path(member).name).write_bytes(f.read())


def noseal(gds, out):
    """pdkv_Top without the seal ring instance and the chip boundary (layer 0), as assemble.py builds it by
    default; False (nothing written) when the chip has no seal ring."""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    seal = [i for i in top.each_inst() if i.cell.name == "pdkv_SEAL"]
    if not seal:
        return False
    cell = seal[0].cell
    seal[0].delete()
    cell.prune_cell()
    li = ly.find_layer(0, 0)
    if li is not None:
        top.shapes(li).clear()
    ly.write(str(out))
    return True


def pad_cells(gds):
    """Boxes (um) of the pad ring's cells in the chip: results there are ETRI's GPIO cells, not ours."""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    pad = [i for i in top.each_inst() if i.cell.name == "pdkv_Pad"][0]
    out = []
    for sub in pad.cell.each_inst():
        b = sub.cell.dbbox().transformed(pad.dcplx_trans * sub.dcplx_trans)
        out.append([round(v, 3) for v in (b.left, b.bottom, b.right, b.top)])
    return out


def expected(gds, has_seal):
    """What our checks predict outside ETRI's pad cells: the Calibre-only checks (calibre_rules.py) give
    the markers; the kit deck and the document's rules 7-12 (metal_rules.py) give none there."""
    lo, found, notes = calibre_rules.run(gds)
    known = []
    for rule, boxes in sorted(found.items()):
        for box, in_zone in boxes:
            if in_zone:
                continue
            b = kdb.DBox.from_s(box)
            known.append({"rule": rule, "box": [round(v, 3) for v in (b.left, b.bottom, b.right, b.top)]})
    return known


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=CHIP / "build/pdkv_Top.gds")
    ap.add_argument("--out", type=Path, default=CHIP / "build/calibre")
    a = ap.parse_args(argv)
    kit = kit_dir()
    out = a.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    decks(kit, out)
    with gzip.open(kit / PONG / "pong_pt1_Top_Pad.gds.gz") as f:
        (out / "pong_pt1_Top_Pad.gds").write_bytes(f.read())
    shutil.copy(kit / PONG / "pong_pt1_Pad.drc.summary", out / "pong_pt1_Pad.drc.summary.etri")
    shutil.copy(a.gds, out / "pdkv_Top.gds")
    has_seal = noseal(a.gds, out / "pdkv_Top_noseal.gds")
    (out / "drc_pong.cal").write_text(DRC_HEADER.format(
        what="1. pong_pt1 (MPW2025 STD-II, fabricated): ETRI's run; the counts must be those of "
             "pong_pt1_Pad.drc.summary.etri", gds="pong_pt1_Top_Pad.gds", top="pong_pt1_Pad", out="pong_pt1_Pad"))
    (out / "drc_pdkv_Top.cal").write_text(DRC_HEADER.format(
        what="2a. pdkv_Top as submitted", gds="pdkv_Top.gds", top="pdkv_Top", out="pdkv_Top"))
    if has_seal:
        (out / "drc_pdkv_Top_noseal.cal").write_text(DRC_HEADER.format(
            what="2b. pdkv_Top without seal ring and chip boundary (as the default build)", gds="pdkv_Top_noseal.gds",
            top="pdkv_Top", out="pdkv_Top_noseal"))
    (out / "ant_pdkv_Top.cal").write_text(ANT_HEADER)
    (out / "lvs_pdkv_Core.cal").write_text(LVS_HEADER)
    run = out / "run_calibre.sh"
    run.write_text(RUN.format(noseal=NOSEAL_LINE if has_seal else ""))
    run.chmod(0o755)
    if lvs_inputs.main(["--gds", str(a.gds), "--out", str(out)]):
        raise SystemExit("LVS inputs failed their checks")
    shutil.copy(HERE / "compare.py", out / "compare.py")
    exp = {"die": [0.0, 0.0, 1900.0, 1900.0], "seal_ring": RING if has_seal else 0.0, "seal_rules": SEAL_RULES,
           "pad_cells": pad_cells(a.gds), "known": expected(a.gds, has_seal),
           "known_why": {"1.PWL.bad2": "CBCM n+ junction test cells 6 and 7 (n+ on the substrate, no DIODE "
                                       "marker; asked ETRI, addendum 3)"}}
    (out / "expected.json").write_text(json.dumps(exp, indent=1))
    tgz = out.parent / "pdkv_calibre.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        tf.add(out, arcname="pdkv_calibre")
    print(f"{out}: " + ", ".join(sorted(p.name for p in out.iterdir())))
    print(f"{tgz} ({tgz.stat().st_size // 1024} KiB): copy, unpack, bash pdkv_calibre/run_calibre.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
