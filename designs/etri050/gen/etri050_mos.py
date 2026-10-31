#!/usr/bin/env python3
"""ETRI 0.5 um MOS test transistors, generated from code and drawn by Magic.

Python works out the geometry on Magic's lambda grid (1 lambda = 0.3 um) and
writes a Magic Tcl script; Magic (batch mode, kit technology) draws the cell,
so contact cuts, implants and wells come out exactly as Magic's ETRI GDS style
makes them. Each cell gets a matching schematic netlist for LVS.

  python3 designs/etri050/gen/etri050_mos.py                     # v0 table -> cells + array, all checks
  python3 designs/etri050/gen/etri050_mos.py nmos:18:0.6 pmos:9:1.2 --check
  python3 designs/etri050/gen/etri050_mos.py --table my.csv --array my_array --out build_dir

Cell layout (single finger, 4 terminals, labels are Magic ports in the order D G S B):

        [ G poly contact ]
   +----+------+----+
   | S  | gate | D  |      S/D contacts run the full width W
   +----+------+----+
   [   body tap  (B)   ]   p+ tap for NMOS, n+ tap in the N-well for PMOS

Limits from the Magic rules: W >= 1.8 um, L >= 0.6 um, both multiples of 0.3 um.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LAMBDA_UM = 0.3
REPO = Path(__file__).resolve().parents[3]
DEFAULT_TABLE = REPO / "designs/etri050/teg/devices_v0.csv"
DEFAULT_OUT = REPO / "designs/etri050/teg/build"

# Geometry in lambda. Values chosen so that both Magic's rules and the official
# NSPL rules hold (cut-to-gate 1.2 um >= 0.75, poly-cut-to-ACT 1.5 um >= 1.0,
# ACT beyond gate 2.4 um >= 0.85, NWELL beyond P+ ACT 1.8 um >= 1.4).
CONTACT = 6      # contact tile (one 0.6 um cut with 0.6 um border)
GATE_GAP = 2     # S/D contact tile to gate
ENDCAP = 2       # poly beyond ACT
PC_GAP = 3       # top of S/D metal to the gate contact (metal1 spacing is 3)
TAP_GAP = 4      # poly end-cap to body tap
WELL_ENC = 6     # N-well beyond P+ active and the n+ tap

KINDS = {
    "nmos": dict(diff="ndiffusion", sd="ndcontact", tap="psubstratepcontact", well=None, model="nfet"),
    "pmos": dict(diff="pdiffusion", sd="pdcontact", tap="nsubstratencontact", well="nwell", model="pfet"),
}


def to_lambda(value_um: float, what: str, minimum: int) -> int:
    n = round(value_um / LAMBDA_UM)
    if not math.isclose(n * LAMBDA_UM, value_um, abs_tol=1e-6):
        raise ValueError(f"{what} = {value_um} um is not a multiple of {LAMBDA_UM} um (Magic lambda grid)")
    if n < minimum:
        raise ValueError(f"{what} = {value_um} um is below the minimum {minimum * LAMBDA_UM:.1f} um")
    return n


def um_text(value_um: float) -> str:
    """18 -> '18', 0.6 -> '0p6' (for cell names)."""
    return f"{value_um:g}".replace(".", "p")


@dataclass(frozen=True)
class Mos:
    kind: str
    w_um: float
    l_um: float
    note: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"kind must be nmos or pmos, not {self.kind!r}")
        to_lambda(self.w_um, "W", CONTACT)
        to_lambda(self.l_um, "L", 2)

    @property
    def name(self) -> str:
        return f"{self.kind}_w{um_text(self.w_um)}_l{um_text(self.l_um)}"

    @property
    def w(self) -> int:
        return to_lambda(self.w_um, "W", CONTACT)

    @property
    def l(self) -> int:
        return to_lambda(self.l_um, "L", 2)

    # ---- geometry (lambda, origin at the lower-left of the active area) ----
    def rects(self):
        """[(magic_layer, x0, y0, x1, y1, label_or_None)] in drawing order."""
        k = KINDS[self.kind]
        w, l = self.w, self.l
        gx0 = CONTACT + GATE_GAP
        gx1 = gx0 + l
        xact = gx1 + GATE_GAP + CONTACT
        pc_w = max(CONTACT, l)
        px0 = gx0 - (pc_w - l) // 2
        pc_y0 = w + PC_GAP
        tap_y1 = -ENDCAP - TAP_GAP
        tap_y0 = tap_y1 - CONTACT
        out = []
        if k["well"]:
            x0, y0, x1, y1 = self.active_bbox()
            out.append((k["well"], x0 - WELL_ENC, y0 - WELL_ENC, x1 + WELL_ENC, y1 + WELL_ENC, None))
        out += [
            (k["diff"], 0, 0, xact, w, None),
            (k["sd"], gx1 + GATE_GAP, 0, xact, w, "D"),
            ("polysilicon", gx0, -ENDCAP, gx1, pc_y0, None),
            ("polycontact", px0, pc_y0, px0 + pc_w, pc_y0 + CONTACT, "G"),
            (k["sd"], 0, 0, CONTACT, w, "S"),
            (k["tap"], 0, tap_y0, xact, tap_y1, "B"),
        ]
        return out

    def active_bbox(self):
        """Bounding box of the ACT shapes (device + tap) in lambda."""
        xact = 2 * CONTACT + 2 * GATE_GAP + self.l
        return 0, -ENDCAP - TAP_GAP - CONTACT, xact, self.w

    def bbox(self):
        xs, ys = [], []
        for _, x0, y0, x1, y1, _ in self.rects():
            xs += [x0, x1]
            ys += [y0, y1]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- outputs ----
    def magic_tcl(self) -> str:
        lines = [f"load {self.name}"]
        labels = []
        for layer, x0, y0, x1, y1, label in self.rects():
            lines.append(f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}")
            lines.append(f"paint {layer}")
            if label:
                labels.append((label, x0, y0, x1, y1))
        for label, x0, y0, x1, y1 in labels:     # D, G, S, B -> ports 1..4
            lines.append(f"box {um(x0)} {um(y0)} {um(x1)} {um(y1)}")
            lines.append(f"label {label}")
        bx0, by0, bx1, by1 = self.bbox()
        lines.append(f"box {um(bx0 - 1)} {um(by0 - 1)} {um(bx1 + 1)} {um(by1 + 1)}")
        lines.append("port makeall")
        lines.append(f"save {self.name}")
        return "\n".join(lines) + "\n"

    def netlist(self) -> str:
        m = KINDS[self.kind]["model"]
        return (f"* {self.name}: drawn W = {self.w_um:g} um, L = {self.l_um:g} um"
                + (f" ({self.note})" if self.note else "") + "\n"
                f".subckt {self.name} D G S B\n"
                f"M1 D G S B {m} W={self.w_um:g}u L={self.l_um:g}u\n"
                ".ends\n")


def um(n: float) -> str:
    return f"{n * LAMBDA_UM:.2f}um"


# --------------------------------------------------------------------------
def magicrc() -> str:
    rc = os.environ.get("ETRI050_MAGICRC")
    if not rc:
        dk = os.environ.get("ETRI050_DK", str(REPO / ".pdk/ETRI050_DesignKit"))
        rc = os.path.join(dk, "tech/etri050.magicrc")
    if not os.path.isfile(rc):
        sys.exit(f"Magic startup file not found: {rc}\n(run: bash scripts/setup-etri050.sh)")
    return rc


def run_magic(script: str, cwd: Path, log: str) -> None:
    res = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", magicrc()],
                         input=script + "quit -noprompt\n", text=True, cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (cwd / log).write_text(res.stdout)


def etri_check(cell: str, sch: str | None, cwd: Path) -> tuple[bool, str]:
    """Run the etri-check shell helper (Magic DRC, GDS, KLayout DRC, LVS)."""
    cmd = 'source "$0" && etri-check "$1" "$2"'
    res = subprocess.run(["bash", "-c", cmd, str(REPO / "scripts/etri050-env.sh"), cell, sch or ""],
                         cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = next((s for s in res.stdout.splitlines() if s.startswith("ETRI-CHECK")), res.stdout.strip())
    return res.returncode == 0, line


def build_cell(dev: Mos, out: Path) -> None:
    for ext in (".mag", ".ext", ".spice", ".gds"):
        (out / f"{dev.name}{ext}").unlink(missing_ok=True)
    run_magic(dev.magic_tcl(), out, f"{dev.name}_build.log")
    if not (out / f"{dev.name}.mag").exists():
        sys.exit(f"Magic did not write {dev.name}.mag (see {out / (dev.name + '_build.log')})")
    (out / "sch").mkdir(exist_ok=True)
    (out / "sch" / f"{dev.name}.spice").write_text(dev.netlist())


def build_array(name: str, devs: list[Mos], out: Path, gap_um: float = 12.0) -> None:
    """Place the cells in rows by kind (unrouted), for viewing and whole-layout DRC."""
    gap = round(gap_um / LAMBDA_UM)
    lines = [f"load {name}"]
    y = 0
    for kind in KINDS:
        row = [d for d in devs if d.kind == kind]
        if not row:
            continue
        x = 0
        top = max(d.bbox()[3] - d.bbox()[1] for d in row)
        for d in row:
            bx0, by0, bx1, by1 = d.bbox()
            lines.append(f"box {um(x)} {um(y)} {um(x)} {um(y)}")
            lines.append(f"getcell {d.name}")
            x += (bx1 - bx0) + gap
        y += top + gap
    lines.append(f"save {name}")
    (out / f"{name}.mag").unlink(missing_ok=True)
    run_magic("\n".join(lines) + "\n", out, f"{name}_build.log")


def read_table(path: Path) -> list[Mos]:
    devs = []
    with open(path, newline="") as f:
        rows = [r for r in f if r.strip() and not r.lstrip().startswith("#")]
    for r in csv.DictReader(rows):
        devs.append(Mos(r["kind"].strip(), float(r["w_um"]), float(r["l_um"]), (r.get("note") or "").strip()))
    return devs


def parse_spec(spec: str) -> Mos:
    m = re.fullmatch(r"(nmos|pmos):([\d.]+):([\d.]+)", spec)
    if not m:
        raise ValueError(f"cell spec must look like nmos:18:0.6 (kind:W:L in um), not {spec!r}")
    return Mos(m[1], float(m[2]), float(m[3]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cells", nargs="*", help="kind:W:L in um, e.g. nmos:18:0.6 (default: the table)")
    ap.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="CSV with kind,w_um,l_um,note")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: %(default)s)")
    ap.add_argument("--array", default=None, help="also place all cells in one top cell with this name")
    ap.add_argument("--check", action="store_true", help="run Magic DRC, KLayout DRC and LVS on every cell")
    args = ap.parse_args(argv)

    try:
        devs = [parse_spec(s) for s in args.cells] if args.cells else read_table(args.table)
    except (ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not args.cells:            # table mode: build the array and check by default
        args.check = True
        args.array = args.array or args.table.stem.replace("devices", "teg")
    names = [d.name for d in devs]
    if len(set(names)) != len(names):
        print("error: the same W/L appears twice", file=sys.stderr)
        return 2

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for d in devs:
        build_cell(d, out)
    print(f"built {len(devs)} cell(s) in {out}")
    if args.array:
        build_array(args.array, devs, out)
        print(f"array: {args.array}.mag")

    ok_all = True
    if args.check:
        for d in devs:
            ok, line = etri_check(d.name, f"sch/{d.name}.spice", out)
            ok_all &= ok
            print(("PASS  " if ok else "FAIL  ") + line)
        if args.array:
            ok, line = etri_check(args.array, None, out)
            ok_all &= ok
            print(("PASS  " if ok else "FAIL  ") + line)
            print(f"view: klayout-etri {out / (args.array + '.gds')}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
