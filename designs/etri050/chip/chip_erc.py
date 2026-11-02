#!/usr/bin/env python3
"""Electrical rule checks of the chip core as drawn: the netlist chip_lvs.py extracts from pdkv_Top.gds
(every device and every net as drawn, nets named after the reference on a match) and its layout.

  gates      every MOS gate is driven: its net reaches a pad port through MOS sources / drains and
             resistors (a DC path; the supplies are pad nets too). A gate net that reaches only other
             gates, bulks or capacitors floats, and so does one behind switches that lead nowhere (the
             array gates when AG is cut from its pad). The pins chip_lvs.py adds at block ports to anchor
             the match (array selects, CBCM enables and nodes) are not pads and drive nothing
  open ends  nets with a single device terminal and no pad (a source, drain or resistor end that leads
             nowhere) and nets with no device terminal and no pin (metal that connects nothing): listed
  wells      every N-well reaches an n+ tap or a PNP base contact (else the well floats); every PMOS
             bulk is an N-well net with a pad (VDD or a pad of its own); every NMOS bulk is the
             substrate, which is VSS. KLayout's soft connections (the deck's SCONNECT) do not put a well
             into its tap's net when no device terminal sits on the well: such a well (the PNP base
             wells) is an empty net here, and its taps are found on the layout and named by their net
  pads       MOS gates on a pad's net, by the pad cell's port (pins.csv): PANA PADR (series POLY2 and
             diodes) and PIC Y (a buffer) are the protected ways in; a gate on a PANA PAD port (force and
             heater lines, the diodes only) or on a pad without a port of the PADR / Y kind fails
  shorts     MOS with source = drain, resistors and capacitors with both ends on one net: listed by net
             (tie-offs and MOS capacitors are drawn that way on purpose; the list is the record)

usage: python3 designs/etri050/chip/chip_erc.py [--gds build/pdkv_Top.gds]    exit 0 when clean
"""
import argparse
import collections
import sys
from pathlib import Path

import klayout.db as kdb

import chip_lvs

HERE = Path(__file__).resolve().parent
PROTECTED = {"PADR", "Y"}           # PANA's resistor port, PIC's buffer output
SUPPLY_PORTS = {"VDD", "VSS"}       # PVDD / PVSS


def box(lv, L, net, layer="m1"):
    """Where a net lies (um), on one layer or else on the first metal that has it."""
    for k in (layer, "m1", "m2", "m3"):
        r = lv.shapes_of_net(net, L[k], True)
        if not r.is_empty():
            b = r.bbox()
            return f"{k} ({b.left / 1000:.1f}, {b.bottom / 1000:.1f})-({b.right / 1000:.1f}, {b.top / 1000:.1f})"
    return "nowhere"


def erc(gds):
    good, rep, nl, keep = chip_lvs.lvs(gds, named=True, keep=True)
    top = next(nl.each_circuit_top_down())
    out, bad = [], False
    if not good:                                              # still checked, nets named as drawn
        out.append("(chip LVS does not match: nets named as drawn)")
    port_of = {name: port for name, net, pad, rect, port in chip_lvs.pad_pins()}
    pads = collections.defaultdict(set)                       # net -> port kinds of its pad pins
    for n in top.each_net():
        for p in n.each_pin():
            if p.pin().name() in port_of:
                pads[n.expanded_name()].add(port_of[p.pin().name()])

    def terms(n):
        return [(t.device().device_class().name, t.terminal_def().name, t.device()) for t in n.each_terminal()]

    # DC groups: nets joined through MOS source-drain and resistors; a group with a pad net is driven
    group = {}

    def find(x):
        while group.get(x, x) != x:
            group[x] = group.get(group[x], group[x])
            x = group[x]
        return x

    for d in top.each_device():
        pair = {"NFET": ("S", "D"), "PFET": ("S", "D"), "P2RES": ("A", "B")}.get(d.device_class().name)
        if pair:
            a, b = (find(d.net_for_terminal(d.device_class().terminal_id(t)).cluster_id) for t in pair)
            if a != b:
                group[a] = b
    driven = {find(n.cluster_id) for n in top.each_net() if n.expanded_name() in pads}

    lv, L = keep["lv"], keep["L"]
    ntap, pnp_bc = lv.layer_by_name("ntap"), lv.layer_by_name("pnp_bc")
    floating, single, empty, bare_wells = [], [], [], []
    for n in top.each_net():
        ts, pins = terms(n), n.pin_count()
        padded = n.expanded_name() in pads
        gates = [d for c, t, d in ts if t == "G"]
        if gates and find(n.cluster_id) not in driven:
            floating.append(f"{n.expanded_name()} ({len(gates)} gates)")
        if len(ts) == 1 and not padded:
            single.append(f"{n.expanded_name()} ({ts[0][0]} {ts[0][1]})")
        if not ts and not pins:
            (bare_wells if not lv.shapes_of_net(n, L["nwell"], True).is_empty() else empty).append(n)
    bad |= bool(floating)
    out.append(f"gates: {'none floating' if not floating else f'{len(floating)} gate nets float: ' + ', '.join(floating[:20])}"
               f" (DC groups through source-drain and resistors: {len(driven)} reach a pad)")
    out.append(f"open ends: {len(single)} nets with one device terminal and no pad"
               + (": " + ", ".join(single[:20]) if single else "")
               + f"; {len(empty)} pieces of wiring with no device or pin"
               + (": " + ", ".join(f"{n.expanded_name()} at {box(lv, L, n)}" for n in empty[:10]) if empty else ""))

    # wells: the N-well shapes and the taps of each net; wells without a device terminal on the layout
    names = keep["names"]
    circ = next(lv.netlist().each_circuit_top_down())
    wells, untied = [], []
    for n in circ.each_net():
        if lv.shapes_of_net(n, L["nwell"], True).is_empty():
            continue
        nm = names.get(n.cluster_id, n.expanded_name())
        wells.append(nm)
        if lv.shapes_of_net(n, ntap, True).is_empty() and lv.shapes_of_net(n, pnp_bc, True).is_empty():
            untied.append(nm)
    taps = [(r, lay) for lay in (ntap, pnp_bc) for r in lay.each()]
    bare = []
    for n in bare_wells:
        w = lv.shapes_of_net(n, L["nwell"], True)
        tied = set()
        for poly, lay in taps:
            if not (w & kdb.Region(poly)).is_empty():
                c = poly.bbox().center()
                t = lv.probe_net(lay, kdb.DPoint(c.x * keep["ly"].dbu, c.y * keep["ly"].dbu))
                tied.add(names.get(t.cluster_id, t.expanded_name()) if t is not None else "?")
        bare.append(f"{box(lv, L, n, 'nwell')} by {'/'.join(sorted(tied)) or 'nothing'}")
        if not tied or "?" in tied:
            untied.append(f"N-well at {box(lv, L, n, 'nwell')}")
    bulks = collections.defaultdict(collections.Counter)
    for d in top.each_device():
        c = d.device_class().name
        if c in ("NFET", "PFET"):
            b = d.net_for_terminal(d.device_class().terminal_id("B"))
            bulks[c][b.expanded_name()] += 1
    pmos_bad = [w for w in bulks["PFET"] if w not in wells or w not in pads]
    nmos_bad = [w for w in bulks["NFET"] if "VSS" not in pads[w]]          # the substrate is PVSS's net
    bad |= bool(untied or pmos_bad or nmos_bad)
    out.append(f"wells: {len(wells)} N-well nets ({', '.join(sorted(wells))}) and {len(bare)} wells without a "
               f"device terminal ({'; '.join(bare)}), " + ("all tied" if not untied else f"untied: {', '.join(untied)}"))
    out.append("PMOS bulks: " + ", ".join(f"{w} {k}" for w, k in sorted(bulks["PFET"].items()))
               + ("" if not pmos_bad else f" -- not a padded N-well: {', '.join(pmos_bad)}"))
    out.append("NMOS bulks: " + ", ".join(f"{w} {k}" for w, k in sorted(bulks["NFET"].items()))
               + ("" if not nmos_bad else " -- not the substrate (VSS)"))

    # gates on pad nets, by port
    rows, exposed = [], []
    for n in top.each_net():
        nm = n.expanded_name()
        if nm not in pads or pads[nm] & SUPPLY_PORTS:
            continue
        g = [d for c, t, d in terms(n) if t == "G"]
        if not g:
            continue
        w = sum(d.parameter("W") for d in g)
        rows.append(f"{nm} [{'/'.join(sorted(pads[nm]))}] {len(g)} gates W {w:.1f} um")
        if not pads[nm] & PROTECTED or "PAD" in pads[nm]:
            exposed.append(nm)
    bad |= bool(exposed)
    out.append("gates on pad nets: " + "; ".join(rows)
               + ("" if not exposed else f" -- on an unprotected port: {', '.join(exposed)}"))

    # devices with two terminals on one net
    shorts = collections.Counter()
    for d in top.each_device():
        c = d.device_class().name
        pairs = {"NFET": ("S", "D"), "PFET": ("S", "D"), "P2RES": ("A", "B"), "PIP": ("A", "B")}.get(c)
        if pairs:
            a, b = (d.net_for_terminal(d.device_class().terminal_id(t)) for t in pairs)
            if a.cluster_id == b.cluster_id:
                g = d.net_for_terminal(d.device_class().terminal_id("G")).expanded_name() if c in ("NFET", "PFET") else "-"
                shorts[(c, a.expanded_name(), g)] += 1
    out.append(f"shorted devices: {sum(shorts.values())}" + ("" if not shorts else ": " + ", ".join(
        f"{c} {n} (gate {g}) x{k}" for (c, n, g), k in sorted(shorts.items()))))
    out.append("chip core ERC: " + ("CLEAN" if not bad else "PROBLEMS"))
    return not bad, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    a = ap.parse_args(argv)
    ok, out = erc(a.gds)
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
