#!/usr/bin/env python3
"""Reads a pdkv Calibre run back (the folder make_run.py writes, after run_calibre.sh). Python 3 only, no
KLayout, so it runs on the Calibre machine too.

  1. pong_pt1: every rule check's count and every layer's geometry count must equal ETRI's summary
     (pong_pt1_Pad.drc.summary.etri): then this Calibre and its settings check a GDS as ETRI's run did.
  2. pdkv_Top (and pdkv_Top_noseal): each result is sorted by where it lies (expected.json):
       pad cells   inside ETRI's GPIO cells (identical to ETRI's library; ETRI's pong run had results there too)
       seal ring   in the seal ring's 30 um, of a check the ring is known to give (contact and via widths,
                   which the deck's history says are waived there, 2.ACT.E5 and 6.PSD.E)
       known       a place our checks predicted (the CBCM n+ junction cells, 1.PWL.bad2)
       UNEXPECTED  anything else: our checks missed it, see the coordinates (um, chip)
  3. pdkv_Top antenna: results, if any (our check of the rule document's antenna rules is clean).
  4. pdkv_Core LVS: the report's verdict (CORRECT expected) and its summary lines.

usage: python3 compare.py [<run folder>]      exit 0 when pong matches, nothing is unexpected and LVS is CORRECT
"""
import json
import re
import sys
from pathlib import Path


def summary(path):
    """({rule check: count}, {layer: geometry count}, total) from a Calibre DRC summary (the flat counts)."""
    rules, layers, total, section = {}, {}, None, None
    for line in Path(path).read_text(errors="replace").split("\n"):
        if line.startswith("--- "):
            section = line[4:].strip()
            continue
        m = re.match(r"^RULECHECK\s+(\S+)\s+\.*\s*TOTAL Result Count = (\d+)\s+\((\d+)\)", line)
        if m and section == "RULECHECK RESULTS STATISTICS":
            rules[m.group(1)] = int(m.group(3))
        m = re.match(r"^LAYER\s+(\S+)\s+\.*\s*TOTAL Original Geometry Count = (\d+)\s+\((\d+)\)", line)
        if m:
            layers[m.group(1)] = int(m.group(3))
        m = re.match(r"^TOTAL DRC Results Generated:\s+(\d+)\s+\((\d+)\)", line)
        if m:
            total = int(m.group(2))
    return rules, layers, total


def results(path):
    """{rule check: [[(x, y) um, chip coordinates]]} from a Calibre ASCII results database. A 'CN <cell> c
    m11 m12 m21 m22 dx dy' line puts the results after it in that cell's space (CELL SPACE XFORM); it holds
    until the next CN line."""
    lines = Path(path).read_text(errors="replace").split("\n")
    prec = float(lines[0].split()[1])
    out, rule, i = {}, None, 1
    xf = (1, 0, 0, 1, 0, 0)
    while i < len(lines):
        t = lines[i].split()
        if len(t) == 1 and re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$", t[0]) and i + 1 < len(lines) \
                and re.match(r"^\d+ \d+ \d+ ", lines[i + 1]):
            rule = t[0]
            out.setdefault(rule, [])
            i += 2 + int(lines[i + 1].split()[2])           # the count line and the check's comment lines
            xf = (1, 0, 0, 1, 0, 0)
            continue
        if t and t[0] in ("p", "e") and rule and len(t) >= 2:
            k = int(t[2]) if t[0] == "p" else 2
            pts = []
            while len(pts) < k and i + 1 < len(lines):
                i += 1
                v = lines[i].split()
                if v and v[0] == "CN":
                    xf = tuple(int(x) for x in v[3:9]) if len(v) >= 9 and v[2] == "c" else (1, 0, 0, 1, 0, 0)
                elif t[0] == "e" and len(v) == 4:
                    pts += [(int(v[0]), int(v[1])), (int(v[2]), int(v[3]))]
                elif len(v) == 2:
                    pts.append((int(v[0]), int(v[1])))
            a, b, c, d, dx, dy = xf
            out[rule].append([((a * x + b * y + dx) / prec, (c * x + d * y + dy) / prec) for x, y in pts])
        i += 1
    return out


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def inside(pt, box, tol=0.05):
    return box[0] - tol <= pt[0] <= box[2] + tol and box[1] - tol <= pt[1] <= box[3] + tol


def in_pad_cells(b, cells):
    """The box b lies in the pad cells' boxes (it may span neighbours): sampled on a grid of 50 x 50 at most."""
    def steps(a, z):
        n = max(1, min(50, int((z - a) / 1.0)))
        return [a + (z - a) * k / n for k in range(n + 1)]
    return all(any(inside((x, y), c) for c in cells) for x in steps(b[0], b[2]) for y in steps(b[1], b[3]))


def where(rule, pts, exp):
    """'pad cells', 'seal ring', 'known' or 'UNEXPECTED' for one result."""
    if in_pad_cells(bbox(pts), exp["pad_cells"]):
        return "pad cells"
    ring, die = exp["seal_ring"], exp["die"]
    if ring and rule in exp["seal_rules"]:
        def depth(p):
            return min(p[0] - die[0], die[2] - p[0], p[1] - die[1], die[3] - p[1])
        if all(-0.1 <= depth(p) <= ring + 0.1 for p in pts):
            return "seal ring"
    b = bbox(pts)
    for k in exp["known"]:
        kb = k["box"]
        if k["rule"] == rule and b[0] <= kb[2] + 0.05 and kb[0] <= b[2] + 0.05 and b[1] <= kb[3] + 0.05 \
                and kb[1] <= b[3] + 0.05:
            return "known"
    return "UNEXPECTED"


def drc(folder, name, exp):
    res = folder / f"{name}.drc.results"
    if not res.exists():
        print(f"{name}: no {res.name} (not run?)")
        return None
    found = results(res)
    rules, _, total = summary(folder / f"{name}.drc.summary") if (folder / f"{name}.drc.summary").exists() \
        else ({}, {}, None)
    print(f"{name}: {sum(len(v) for v in found.values())} results in the database"
          + (f" (summary: {total} flat)" if total is not None else ""))
    bad = 0
    for rule in sorted(found, key=lambda r: [int(x) if x.isdigit() else x for x in re.split(r"[.]", r)]):
        if not found[rule]:
            continue
        kinds = {}
        for pts in found[rule]:
            kinds.setdefault(where(rule, pts, exp), []).append(pts)
        flat = f" (flat {rules[rule]})" if rule in rules and rules[rule] != len(found[rule]) else ""
        print(f"  {rule}: {len(found[rule])}{flat}  " + ", ".join(f"{k} {len(v)}" for k, v in sorted(kinds.items())))
        for pts in kinds.get("UNEXPECTED", [])[:10]:
            b = bbox(pts)
            print(f"      UNEXPECTED at ({b[0]:.3f}, {b[1]:.3f}) - ({b[2]:.3f}, {b[3]:.3f})")
        bad += len(kinds.get("UNEXPECTED", []))
    for k in exp["known"]:
        hit = any(where(k["rule"], pts, exp) == "known" and inside(((bbox(pts)[0] + bbox(pts)[2]) / 2,
                  (bbox(pts)[1] + bbox(pts)[3]) / 2), k["box"], 1.0) for pts in found.get(k["rule"], []))
        if not hit:
            print(f"  predicted but not found: {k['rule']} at {k['box']} ({exp['known_why'].get(k['rule'], '')})")
    print(f"  -> {'nothing unexpected' if not bad else f'{bad} UNEXPECTED'}"
          + "".join(f"; {r}: {why}" for r, why in exp["known_why"].items() if r in found))
    return bad


def main(argv=None):
    folder = Path((argv or sys.argv[1:] or ["."])[0])
    exp = json.loads((folder / "expected.json").read_text())
    ok = True
    print("== 1. pong_pt1 against ETRI's summary")
    mine, etri = folder / "pong_pt1_Pad.drc.summary", folder / "pong_pt1_Pad.drc.summary.etri"
    if mine.exists():
        r1, l1, t1 = summary(mine)
        r0, l0, t0 = summary(etri)
        rd = {k: (r1.get(k), r0.get(k)) for k in set(r0) | set(r1) if r1.get(k) != r0.get(k)}
        ld = {k: (l1.get(k), l0.get(k)) for k in set(l0) | set(l1) if l1.get(k) != l0.get(k)}
        print(f"  rule checks {len(r1)} (ETRI {len(r0)}), results {t1} (ETRI {t0}), layers {len(l1)} (ETRI {len(l0)})")
        for k, (a, b) in sorted(rd.items()):
            print(f"  DIFFERS {k}: {a}, ETRI {b}")
        for k, (a, b) in sorted(ld.items()):
            print(f"  DIFFERS layer {k}: {a}, ETRI {b}")
        same = not rd and not ld and t1 == t0
        ok &= same
        print("  -> " + ("same as ETRI's run" if same else "NOT the same as ETRI's run: settings or Calibre differ"))
    else:
        print("  not run")
        ok = False
    print("== 2. pdkv_Top DRC")
    for name in ("pdkv_Top", "pdkv_Top_noseal"):
        e = dict(exp, seal_ring=0.0) if name.endswith("noseal") else exp
        bad = drc(folder, name, e)
        if bad is not None or name == "pdkv_Top":                 # the variant without seal ring is optional
            ok &= bad == 0
    print("== 3. pdkv_Top antenna")
    ant = folder / "pdkv_Top.ant.results"
    if ant.exists():
        found = {k: v for k, v in results(ant).items() if v}
        n = sum(len(v) for v in found.values())
        print(f"  {n} results" + "".join(f"\n  {k}: {len(v)}, e.g. at {bbox(v[0])}" for k, v in sorted(found.items())))
        ok &= n == 0
    else:
        print("  not run")
    print("== 4. pdkv_Core LVS")
    rep = folder / "pdkv_Core.lvs.rep"
    if rep.exists():
        text = rep.read_text(errors="replace")
        verdict = re.findall(r"#\s+(CORRECT|INCORRECT|NOT COMPARED)\s+#", text)
        print(f"  verdict: {verdict[0] if verdict else 'not found in the report'}")
        for line in text.split("\n"):
            if re.search(r"(Error|Warning|INCORRECT|Unmatched|Discrepanc|CELL COMPARISON|ports|nets|instances)", line) \
                    and len(line.strip()) < 140:
                print("   " + line.rstrip())
        ok &= bool(verdict) and verdict[0] == "CORRECT"
    else:
        print("  not run")
    print("compare: " + ("as predicted" if ok else "see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
