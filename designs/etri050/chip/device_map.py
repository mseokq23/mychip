"""Every device of the chip core in a marker database for KLayout's marker browser, block by block.

The devices are the ones chip_lvs.py extracts inside the pad ring (ETRI's Calibre LVS deck's recognition),
as drawn: every MOS finger and every resistor apart, nets named after the reference netlist when the chip
matches. Each device goes into the block that holds the centre of its box (the smallest top-level instance
of pdkv_Top whose box does), then into its type and size (the parameters chip_lvs.py compares: W and L, PIP A and P, PNP AE). A marker is the
device's box; its text gives the parameters and the nets on the terminals. The pad ring (ETRI's GPIO
cells) is not in it, as it is not in the LVS.

usage: python3 designs/etri050/chip/device_map.py [--gds build/pdkv_Top.gds] [--out build/pdkv_devices.lyrdb]
view:  klayout-etri designs/etri050/chip/build/pdkv_Top.gds -m designs/etri050/chip/build/pdkv_devices.lyrdb
       (Marker Browser: block > device type and size > device; a click moves the view to it)
"""
import argparse
import collections
import sys
from pathlib import Path

import klayout.db as kdb
import klayout.rdb as krdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chip_lvs  # noqa: E402

NAMES = {                           # cell -> block name in the browser
    "teg_ctrl_F": "control block",
    "karray": "Kelvin array",
    "cbcm": "CBCM",
    "robank_flat": "RO bank",
    "rores": "resistor RO",
    "mosc": "MOS-C",
    "lsplit": "L-split",
    "heater": "heater",
    "pnp10": "PNP",
}
ORDER = ["L-split", "MOS-C", "PNP1", "PNP2", "heater", "Kelvin array", "CBCM", "RO bank", "resistor RO",
         "control block"]


def blocks(gds: Path):
    """[(name, cell, DBox)] for the top-level instances but the pad ring and seal; two PNPs: PNP1 the
    upper one (beside the L-split), PNP2 the lower one (south-west corner)."""
    ly = kdb.Layout()
    ly.read(str(gds))
    out = []
    for inst in ly.top_cell().each_inst():
        cell = inst.cell.name
        if cell in ("pdkv_Pad", "pdkv_SEAL"):
            continue
        out.append([NAMES.get(cell, cell), cell, inst.dbbox()])
    pnps = sorted((b for b in out if b[1] == "pnp10"), key=lambda b: -b[2].center().y)
    for k, b in enumerate(pnps):
        b[0] = f"PNP{k + 1}"
    return [tuple(b) for b in out]


def size_key(cls, d):
    return " ".join(f"{p} {d.parameter(p):.4g}" for p in chip_lvs.TOL[cls])


def device_map(gds: Path, out: Path):
    good, rep, nl, keep = chip_lvs.lvs(gds, named=True, keep=True)
    lv = keep["lv"]
    il = lv.internal_layout()
    top = nl.circuit_by_name(keep["top"].name)
    bl = blocks(gds)
    found = collections.defaultdict(list)                 # (block, type and size) -> [(box, text)]
    for d in top.each_device():
        cls = d.device_class()
        box = d.trans * il.cell(d.device_abstract.cell_index()).dbbox()
        inside = [b for b in bl if b[2].contains(box.center())]
        block = min(inside, key=lambda b: b[2].area())[0] if inside else "outside the blocks"
        main = " ".join(f"{p}={d.parameter(p):.4g}" for p in chip_lvs.TOL[cls.name])
        nets = " ".join(f"{t.name}={d.net_for_terminal(t.id()).expanded_name() if d.net_for_terminal(t.id()) else '-'}"
                        for t in cls.terminal_definitions())
        rest = " ".join(f"{p.name}={d.parameter(p.name):.4g}" for p in cls.parameter_definitions()
                        if p.name not in chip_lvs.TOL[cls.name] and d.parameter(p.name))
        found[(block, f"{cls.name} {size_key(cls.name, d)}")].append((box, f"{cls.name} {main}; {nets}; {rest}"))

    rdb = krdb.ReportDatabase("pdkv devices")
    rdb.description = (f"devices of the chip core as drawn ({gds.name}, chip_lvs.py extraction, "
                       f"LVS {'match: nets named after the reference' if good else 'NO MATCH: nets unnamed'})")
    rdb.top_cell_name = keep["top"].name
    rcell = rdb.create_cell(keep["top"].name)
    names = sorted({k[0] for k in found}, key=lambda n: (ORDER.index(n) if n in ORDER else len(ORDER), n))
    lines = []
    for name in names:
        subs = sorted(k for k in found if k[0] == name)
        n_block = sum(len(found[k]) for k in subs)
        cat = rdb.create_category(name)
        cat.description = f"{name}: {n_block} devices"
        lines.append(f"{name}: {n_block} devices")
        for k in subs:
            sub = rdb.create_category(cat, k[1])
            sub.description = f"{k[1]}: {len(found[k])}"
            lines.append(f"  {k[1]}: {len(found[k])}")
            for box, text in sorted(found[k], key=lambda e: (-e[0].center().y, e[0].center().x)):
                item = rdb.create_item(rcell.rdb_id(), sub.rdb_id())
                item.add_value(box)
                item.add_value(text)
    out.parent.mkdir(parents=True, exist_ok=True)
    rdb.save(str(out))
    per_type = collections.Counter()
    for (_, k), v in found.items():
        per_type[k.split()[0]] += len(v)
    lines.append("total: " + ", ".join(f"{k} {v}" for k, v in sorted(per_type.items()))
                 + f" ({sum(per_type.values())} devices as drawn, LVS {'MATCH' if good else 'MISMATCH'})")
    return good, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    ap.add_argument("--out", type=Path, default=HERE / "build/pdkv_devices.lyrdb")
    a = ap.parse_args(argv)
    good, lines = device_map(a.gds, a.out)
    print("\n".join(lines))
    print(f"wrote {a.out}; view: klayout-etri {a.gds} -m {a.out}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
