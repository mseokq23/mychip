#!/usr/bin/env python3
"""Inputs for a Calibre LVS of the chip core with ETRI's deck: pdkv_Core.gds and pdkv_Core.cdl.

The pad ring is ETRI's (its GPIO cells have no netlist here) and the precedent's DB form asks the LVS
"for the core only", so the comparison is the core's, as chip_lvs.py does it in KLayout:

  pdkv_Core.gds  pdkv_Top.gds without the pad ring and the seal ring (and its chip boundary), top cell
                 renamed pdkv_Core. Each pad cell's core port (pad_pins.json, metal2) is drawn on metal2 as
                 the pad cell has it, so the core wires that meet in a port meet here too (the three VSS
                 branches in the PVSS port), and carries a MET2TXT (44) label in the top cell (the deck reads
                 TEXT DEPTH PRIMARY) named after its chip net: PVDD -> VDD, PVSS -> VSS, a force and its
                 sense pad -> their node (ASF/ASS -> SRC, LD1F/LD1S -> D1, LSF/LSS -> S, LD2F/LD2S -> D2),
                 the others by their pin. The two PVDD ports reach different core VDD nets (W1: control,
                 array ...; S7: CBCM) that the pad ring joins; the LVS header joins them by name
                 (VIRTUAL CONNECT NAME "VDD").
  pdkv_Core.cdl  the circuit the core was designed as, chip_lvs.py's reference (block schematics, the frozen
                 control netlist, the chip's connections), flattened into one .SUBCKT pdkv_Core with the
                 chip nets as ports, devices in the form of ETRI's design guide (3.3-3.8, the PDK's CDL
                 output): M d g s b nmos4|pmos4 W= L= m=1; R a b $[p2res] w= l=; C a b $[pipcap] w= l=;
                 Q c b e pnpbjt m=1 area= (m2). The deck's DEVICE names are NMOS4, PMOS4, P2RES, PIPCAP,
                 PNPBJT and it traces W, L (MOS, P2RES, PIPCAP) and A (PNP) exactly.

Self-checks: the CDL is read back and must give the reference's devices (class, terminal nets, traced
parameters) one for one; each label must lie on the extracted core net of its name (chip_lvs.py's
extraction of pdkv_Top.gds, which must match).

usage: python3 designs/etri050/chip/calibre/lvs_inputs.py [--gds build/pdkv_Top.gds] [--out build/calibre]
"""
import argparse
import collections
import re
import sys
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
CHIP = HERE.parent
sys.path.insert(0, str(CHIP))
import chip_lvs  # noqa: E402

TOP = "pdkv_Core"
MET2, MET2TXT = 34, 44
MODEL = {"NFET": "nmos4", "PFET": "pmos4", "P2RES": "$[p2res]", "PIP": "$[pipcap]", "PNP": "pnpbjt"}


def um(v):
    """A length in um for the CDL: '9u', '0.6u' (1 nm)."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s + "u"


def pins_by_net():
    """[(chip net, pad, port rect)] and the chip nets in pad order, unique."""
    rows = [(net, pad, rect) for _, net, pad, rect, _ in chip_lvs.pad_pins()]
    order = list(dict.fromkeys(net for net, _, _ in rows))
    return rows, order


def core_gds(gds: Path, out: Path):
    """pdkv_Core.gds; returns [(label, point um)]."""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    gone = []
    for inst in list(top.each_inst()):
        if inst.cell.name in ("pdkv_Pad", "pdkv_SEAL"):
            gone.append(inst.cell)
            inst.delete()
    if "pdkv_Pad" not in [c.name for c in gone]:
        raise SystemExit(f"{gds}: no pdkv_Pad instance")
    for c in gone:
        c.prune_cell()
    cb = ly.find_layer(0, 0)
    if cb is not None:
        top.shapes(cb).clear()
    top.name = TOP
    m2 = ly.layer(MET2, 0)
    txt = ly.layer(MET2TXT, 0)
    labels = []
    rows, _ = pins_by_net()
    for net, pad, (x1, y1, x2, y2) in rows:
        top.shapes(m2).insert(kdb.DBox(x1, y1, x2, y2))
        at = kdb.DPoint(round((x1 + x2) / 2, 2), round((y1 + y2) / 2, 2))
        top.shapes(txt).insert(kdb.DText(net, kdb.DTrans(at.x, at.y)))
        labels.append((net, pad, at))
    if len(ly.top_cells()) != 1:
        raise SystemExit(f"pdkv_Core: top cells {[c.name for c in ly.top_cells()]}")
    ly.write(str(out))
    return labels


def safe_names(circuit, ports):
    """CDL net names by the reference net's (unique) name: the ports as they are, the rest [A-Za-z0-9_],
    unique without regard to case (SPICE)."""
    names, used = {}, {p.upper() for p in ports}
    for n in circuit.each_net():
        raw = n.expanded_name()
        if raw in ports:
            names[raw] = raw
            continue
        base = re.sub(r"[^A-Za-z0-9_]", "_", raw)
        if not base or base[0].isdigit():
            base = "N" + base
        name, k = base, 1
        while name.upper() in used:
            k += 1
            name = f"{base}_{k}"
        used.add(name.upper())
        names[raw] = name
    if len(names) != len(list(circuit.each_net())):
        raise SystemExit("reference: net names are not unique")
    return names


def write_cdl(path: Path):
    """pdkv_Core.cdl from chip_lvs.py's reference; returns {class: count} and the device list for the check."""
    pins = chip_lvs.pad_pins()
    ref, top = chip_lvs.reference_netlist(pins, [])
    _, ports = pins_by_net()
    names = safe_names(top, ports)
    lines = ["* pdkv_Core: the chip core (pdkv_Top without pad ring and seal ring) as designed, written by",
             "* designs/etri050/chip/calibre/lvs_inputs.py from chip_lvs.py's reference netlist (block schematics,",
             "* the frozen control netlist, the chip's connections); devices in the PDK's CDL form (design guide 3.3-3.8)",
             f".SUBCKT {TOP} " + " ".join(ports)]
    count = collections.Counter()
    serial = collections.Counter()                           # instance names unique per element letter
    devices = []
    for d in top.each_device():
        cls = d.device_class().name
        if cls not in MODEL:
            raise SystemExit(f"reference: a {cls} device ({d.expanded_name()})")
        count[cls] += 1
        letter = {"NFET": "M", "PFET": "M", "P2RES": "R", "PIP": "C", "PNP": "Q"}[cls]
        serial[letter] += 1
        k = serial[letter]
        net = lambda t: names[d.net_for_terminal(d.device_class().terminal_id(t)).expanded_name()]
        if cls in ("NFET", "PFET"):
            w, l = d.parameter("W"), d.parameter("L")
            t = (net("D"), net("G"), net("S"), net("B"))
            lines.append(f"M{k} {' '.join(t)} {MODEL[cls]} W={um(w)} L={um(l)} m=1")
            devices.append(("M", t, (round(w, 3), round(l, 3))))
        elif cls == "P2RES":
            w, l = d.parameter("W"), d.parameter("L")
            t = (net("A"), net("B"))
            lines.append(f"R{k} {' '.join(t)} {MODEL[cls]} w={um(w)} l={um(l)}")
            devices.append(("R", t, (round(w, 3), round(l, 3))))
        elif cls == "PIP":
            w, l = chip_lvs.PIP_WL
            if abs(d.parameter("A") - w * l) > 1e-6:
                raise SystemExit(f"PIP area {d.parameter('A')} um2, not {w} x {l}")
            t = (net("A"), net("B"))
            lines.append(f"C{k} {' '.join(t)} {MODEL[cls]} w={um(w)} l={um(l)}")
            devices.append(("C", t, (round(w, 3), round(l, 3))))
        else:
            ae = d.parameter("AE")
            t = (net("C"), net("B"), net("E"))
            lines.append(f"Q{k} {' '.join(t)} {MODEL[cls]} m=1 area={ae * 1e-12:.6g}")
            devices.append(("Q", t, (round(ae, 3),)))
    lines.append(".ENDS")
    path.write_text("\n".join(lines) + "\n")
    return count, devices, ports


def read_cdl(path: Path):
    """The devices of a CDL written above, read back: [(kind, terminal nets, traced parameters)]; instance
    names must be unique."""
    out, ports, seen = [], None, set()
    for line in path.read_text().split("\n"):
        t = line.split()
        if not t or t[0].startswith("*"):
            continue
        if not t[0].startswith(".") and t[0].upper() in seen:
            raise SystemExit(f"{path.name}: instance {t[0]} twice")
        seen.add(t[0].upper())
        if t[0].upper() == ".SUBCKT":
            ports = t[2:]
            continue
        if t[0].upper() == ".ENDS":
            continue
        kind = t[0][0].upper()
        kv = {a.split("=")[0].lower(): a.split("=")[1] for a in t if "=" in a}
        val = lambda s: float(s[:-1]) if s.endswith("u") else float(s)
        if kind == "M":
            out.append(("M", tuple(t[1:5]), (val(kv["w"]), val(kv["l"]))))
        elif kind in "RC":
            out.append((kind, tuple(t[1:3]), (val(kv["w"]), val(kv["l"]))))
        elif kind == "Q":
            out.append(("Q", tuple(t[1:4]), (round(float(kv["area"]) * 1e12, 3),)))
        else:
            raise SystemExit(f"{path.name}: unknown line {line}")
    return out, ports


def check_labels(gds: Path, labels):
    """Each label lies on the extracted core net of its name (chip_lvs.py on pdkv_Top.gds)."""
    good, rep, drawn, x = chip_lvs.lvs(gds, named=True, keep=True)
    if not good:
        raise SystemExit("chip_lvs.py: the core does not match its reference; fix that first\n" + "\n".join(rep))
    lv, L, names = x["lv"], x["L"], x["names"]
    bad = []
    for label, pad, at in labels:
        net = lv.probe_net(L["port"], at)
        for ring in L["ring"]:
            net = net or lv.probe_net(ring, at)
        got = names.get(net.cluster_id) if net is not None else None
        if got != label:
            bad.append(f"{pad} label {label} at {at}: core net {got}")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=CHIP / "build/pdkv_Top.gds")
    ap.add_argument("--out", type=Path, default=CHIP / "build/calibre")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    labels = core_gds(a.gds, a.out / f"{TOP}.gds")
    count, devices, ports = write_cdl(a.out / f"{TOP}.cdl")
    back, back_ports = read_cdl(a.out / f"{TOP}.cdl")
    problems = []
    if back_ports != ports:
        problems.append(f"CDL ports {back_ports}, expected {ports}")
    if collections.Counter(back) != collections.Counter(devices):
        problems.append("CDL read back differs from the reference devices")
    problems += check_labels(a.gds, labels)
    print(f"{TOP}.gds: {len(labels)} pad ports drawn on metal2 with MET2TXT labels ({len(set(l for l, _, _ in labels))} names)")
    print(f"{TOP}.cdl: {len(ports)} ports, devices " + ", ".join(f"{MODEL[k]} {v}" for k, v in sorted(count.items())))
    print("checks: CDL read back = reference devices; every label on the core net of its name (chip_lvs.py match)"
          + ("" if not problems else "\nPROBLEMS:\n  " + "\n  ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
