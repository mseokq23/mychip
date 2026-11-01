#!/usr/bin/env python3
"""Device-level LVS of the resistor RO as it goes on the chip (rores_full.gds), with KLayout.

Netgen (etri-check) compares the Magic layout, in which each resistor is the black box p2r40: it checks
the ring through the resistor heads but never sees POLY2, CONT, LVSD or RES, which KLayout adds after
Magic. This script extracts the final GDS itself:

  NMOS / PMOS  MOS4 from ACT, POLY1, NSD, PSD and NWELL (gate = ACT and POLY1)
  resistor     body = POLY2 and LVSD and RES (the Calibre deck's PPRES), R = 125 ohm/sq x L / W
               (PDK p2res_i RSH), terminals = the POLY2 beyond the body, joined to MET1 by CONT
  wiring       CONT, MET1, VIA1, MET2, VIA2, MET3; N-well to its n+ taps, p+ taps to the substrate

and compares it with the circuit of etri050_ro.py written out at transistor level (the kit's standard
cell netlist) with each resistor as R = 125 x 40 = 5000 ohm. Ports are named from rores_pins.json.

usage: python3 designs/etri050/ro/rores_lvs.py [--gds build/rores_full.gds]   (exit 0 on a match)
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gen"))
import etri050_ro as gen  # noqa: E402
import etri050_cbcm as cb  # noqa: E402

RSH = 125.0                       # PDK p2res_i RSH, ohm/sq


def reference(path: Path):
    """The circuit of etri050_ro.py at transistor level, resistors as plain R (5000 ohm)."""
    order = {"INVX1": "A Y", "INVX4": "A Y", "NAND2X1": "A B Y"}
    i = gen.RES_I
    out = [f"* {gen.RES_NAME}: circuit of etri050_ro.py, resistors {RSH:g} ohm/sq x {gen.R_L_UM / gen.R_W_UM:g} sq",
           cb.kit_stdcells_spice(), f".subckt {gen.RES_NAME} en{i} in{i} VDD VSS"]
    for inst, cell, pins in gen.stage_nets(i, "res"):
        out.append(f"{inst} " + " ".join(pins[p] for p in order[cell].split()) + f" VDD VSS {cell}")
    for inst, pins in gen.resistor_nets(i):
        out.append(f"R{inst[1:]} {pins['A']} {pins['B']} {RSH * gen.R_L_UM / gen.R_W_UM:g}")
    out.append(".ends")
    path.write_text("\n".join(out) + "\n")


def lvs(gds: Path):
    """-> (match, summary line, problems)"""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    sub = ly.layer(999, 0)                       # substrate helper, in memory only
    top.shapes(sub).insert(top.bbox().enlarged(2000))
    lv = kdb.LayoutVsSchematic(kdb.RecursiveShapeIterator(ly, top, []))
    L = {k: lv.make_layer(ly.layer(n, 0), k) for k, n in
         (("nwell", 2), ("act", 11), ("poly1", 12), ("poly2", 13), ("nsd", 14), ("psd", 15), ("cont", 31),
          ("m1", 32), ("v1", 33), ("m2", 34), ("v2", 35), ("m3", 36), ("res", 51), ("lvsd", 60))}
    L["sub"] = lv.make_layer(sub, "sub")
    gate = L["act"] & L["poly1"]
    ngate, pgate = (gate & L["nsd"]) - L["nwell"], gate & L["psd"] & L["nwell"]
    nact, pact = (L["act"] & L["nsd"]) - L["poly1"], (L["act"] & L["psd"]) - L["poly1"]
    nsd, ntap = nact - L["nwell"], nact & L["nwell"]
    psd, ptap = pact & L["nwell"], pact - L["nwell"]
    bulk = L["sub"] - L["nwell"]
    body = L["poly2"] & L["lvsd"] & L["res"]
    term = L["poly2"] - body
    for name, reg in (("ngate", ngate), ("pgate", pgate), ("nsd_sd", nsd), ("ntap", ntap), ("psd_sd", psd),
                      ("ptap", ptap), ("bulk", bulk), ("r_body", body), ("r_term", term)):
        lv.register(reg, name)
    lv.extract_devices(kdb.DeviceExtractorMOS4Transistor("NFET"), {"SD": nsd, "G": ngate, "P": L["poly1"], "W": bulk})
    lv.extract_devices(kdb.DeviceExtractorMOS4Transistor("PFET"), {"SD": psd, "G": pgate, "P": L["poly1"], "W": L["nwell"]})
    lv.extract_devices(kdb.DeviceExtractorResistor("RES", RSH), {"R": body, "C": term})
    for reg in (L["poly1"], term, nsd, psd, ntap, ptap, L["nwell"], L["cont"], L["m1"], L["v1"], L["m2"], L["v2"], L["m3"]):
        lv.connect(reg)
    for reg in (L["poly1"], term, nsd, psd, ntap, ptap):
        lv.connect(L["cont"], reg)
    for a, b in (("cont", "m1"), ("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3")):
        lv.connect(L[a], L[b])
    lv.connect(L["nwell"], ntap)
    lv.connect_global(bulk, "SUBSTRATE")
    lv.connect_global(ptap, "SUBSTRATE")
    lv.extract_netlist()

    circ = next(lv.netlist().each_circuit_top_down())
    pins = json.loads((gds.parent / f"{gen.RES_NAME}_pins.json").read_text())["pins"]
    problems = []
    for name, p in pins.items():
        x0, y0, x1, y1 = p["box"]
        net = lv.probe_net(L["m1" if p["layer"] == "metal1" else "m2"], kdb.DPoint((x0 + x1) / 2, (y0 + y1) / 2))
        if net is None:
            problems.append(f"port {name}: no metal at its box")
            continue
        net.name = name
        circ.connect_pin(circ.create_pin(name), net)
    count = {}
    for d in circ.each_device():
        count[d.device_class().name] = count.get(d.device_class().name, 0) + 1
    rvals = sorted({round(d.parameter("R"), 2) for d in circ.each_device() if d.device_class().name == "RES"})

    with tempfile.TemporaryDirectory() as tmp:
        ref_path = Path(tmp) / "rores_ref.spice"
        reference(ref_path)
        ref = kdb.Netlist()
        ref.read(str(ref_path), kdb.NetlistSpiceReader())
    ref.flatten()
    ref_top = ref.circuit_by_name(gen.RES_NAME.upper()) or ref.circuit_by_name(gen.RES_NAME)
    for c in [c for c in ref.each_circuit() if c.name != ref_top.name]:
        ref.purge_circuit(c)                     # kit cells the ring does not use (NOR2X1) stay unmatched otherwise
    lv.reference = ref
    lv.netlist().combine_devices()
    ref.combine_devices()
    lv.netlist().purge_nets()
    ref.purge_nets()
    cmp = kdb.NetlistComparer()
    cmp.same_circuits(circ, ref_top)
    ok = lv.compare(cmp)
    xref = lv.xref()
    for cp in xref.each_circuit_pair():
        if cp.status() != kdb.NetlistCrossReference.Match:
            problems.append(f"circuit {cp.first().name if cp.first() else '-'} <-> "
                            f"{cp.second().name if cp.second() else '-'}: {cp.status()}")
        for pp in xref.each_pin_pair(cp):
            if pp.status() != kdb.NetlistCrossReference.Match:
                problems.append(f"pin {pp.first().expanded_name() if pp.first() else '-'} <-> "
                                f"{pp.second().expanded_name() if pp.second() else '-'}: {pp.status()}")
        for n in xref.each_net_pair(cp):
            if n.status() != kdb.NetlistCrossReference.Match:
                problems.append(f"net {n.first().expanded_name() if n.first() else '-'} <-> "
                                f"{n.second().expanded_name() if n.second() else '-'}: {n.status()}")
        for d in xref.each_device_pair(cp):
            if d.status() != kdb.NetlistCrossReference.Match:
                problems.append(f"device {d.first().expanded_name() if d.first() else '-'} <-> "
                                f"{d.second().expanded_name() if d.second() else '-'}: {d.status()}")
    lv.write(str(gds.parent / f"{gen.RES_NAME}_device_lvs.lvsdb"))
    line = (f"device LVS (KLayout, final GDS with the POLY2 resistors): {'MATCH' if ok and not problems else 'MISMATCH'}; "
            f"extracted {', '.join(f'{v} {k}' for k, v in sorted(count.items()))}, resistors {rvals} ohm")
    return ok and not problems, line, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=gen.DEFAULT_OUT / f"{gen.RES_NAME}_full.gds")
    args = ap.parse_args(argv)
    ok, line, problems = lvs(args.gds)
    print(line)
    for p in problems[:30]:
        print("  " + p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
