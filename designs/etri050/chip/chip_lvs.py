#!/usr/bin/env python3
"""Device-level LVS of the pdkv chip core: pdkv_Top.gds without its pad ring and seal ring, against the
circuit the chip was designed as (KLayout).

Layout side. Devices and connections are recognized as ETRI's Calibre LVS deck for the process does
(NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_LVS.cal in the ETRI PDK 260820; its layer names in brackets):

  NMOS / PMOS   gate = n+ or p+ active and POLY1, outside / inside NWELL, no CAP, BJT or DIODE marker
                [NACT = (ACT AND NSD) NOT EXTLAYER, NGATE = NOT (NACT AND POLY1) NWELL, PGATE likewise
                inside NWELL]; source / drain = the rest of that active touching the gate [NISD]; W =
                gate edge on source / drain / 2, L = area / W [MOSWL]; bulk: the substrate / the N-well
  taps          n+ in NWELL and p+ outside it, away from POLY1 [NTAP, PTAP], soft-connected to the
                N-well and the substrate as the deck's SCONNECT: a well or the substrate reached by two
                metal nets that the wiring does not join is reported (KLayout's soft-connection log, the
                deck's SOFTCHK) and fails the check, so a block whose ground is cut off still shows up
  P2RES         body = POLY2 and LVSD and RES [PPOLYRES], terminals = the POLY2 of the resistor beyond
                LVSD [PPLY2]; W = body edge on the terminals / 2, L = area / W, compared [TRACE PROPERTY
                W, L]; R = 125 ohm/sq x L / W (PDK p2res_i RSH, reported only)
  PIPCAP        where NSD and CAP [PIPCAP]; contacts reach the top plate on POLY2 over POLY1 [PIP_POS]
                and the bottom plate on POLY1 XOR POLY2 [PIP_NEG]; W = area of the PIPCAP's LVSD / 0.2 um,
                L = area of PIP_POS / W, compared [the deck's PROPERTY W, L], plate area and perimeter too;
                a PIP whose POLY2 leaves its POLY1 is reported
  PNP           under the BJT marker [PNPBJT]: emitter = p+ in BJT and NWELL of 4, 25 or 100 um2,
                base = the n+ inside that N-well, collector = a closed p+ ring outside it (DONUT
                around the emitter's HOLE); emitter area compared [TRACE PROPERTY A]
  wiring        POLY1 outside CAP, CONT, MET1, VIA1, MET2, VIA2, MET3
Every drawn gate (ACT and POLY1), resistor body, PIPCAP, BJT and DIODE marker must have become a device
(the core has no diode, so a DIODE marker is a problem), and no POLY2 may lie outside a device.

Pins. The pad ring is ETRI's (its cells have no netlist here), so the core is cut at the pad cells'
core ports (pad_pins.json from pad_ring.py): every port becomes one pin, named after its pad
(pins.csv). The ports are metal2 (the ring's metal2 covers each port rectangle): core metal2 must
overlap the rectangle and is joined there as the pad cell's port joins it; metal1 or metal3 merely
crossing the rectangle connects nothing. Ports the ring's own metal joins are joined too
(ring_groups() extracts the pad ring placed in this GDS: the two PVDD pads, on its VDD bus; the CBCM's
VDD comes from S7, the rest from W1). A force port (PAD, carries mA) must receive the 9 um force line,
so a force and its sense swapped at the pads shows. The three VSS branches (core, PNP1 + L-split,
heater return) meet only in the PVSS pad (chip_check.py checks that on the metal); here they are one
net through that port.

Anchors. Device-level LVS cannot tell apart blocks of the same devices: the array's NMOS rows 0-7 and
PMOS rows 8-11 are alike, and so are the CBCM cells whose structure has no device (empty, metal plates,
comb, n+ regions). Their block ports (array row and column selects, CBCM enables, from the blocks' pin
files) and each CBCM cell's node where its structure is drawn (the generator's rectangles of ND<i>
inside the cell's structure window, cbcm_c.py) become pins named the same in the layout and in the
reference, so a swap shows as a pin-name difference.

Reference side, all written from the design and not from the drawing:
  karray, cbcm, robank, rores, lsplit, mosc   the blocks' schematic netlists (<block>/build/sch, the
                                              ones their block LVS used); the kit cells they include
                                              must equal the kit's netlist
  cbcm PIP                                    30 x 30 um between ND1 (top plate) and VSS (etri050_cbcm.py)
  rores resistors                             p2r40 = P2RES W 2.0 x L 80.0 um (etri050_ro.py)
  teg_ctrl                                    ctrl/macro/teg_ctrl.spc + the kit cell netlist (FILL empty)
  pnp10                                       PNP, emitter 10 x 10 um (the PDK cell); base, collector VSS
  heater                                      P2RES W 20 x L 120 um (pdk_cells.py), HT to VSS
  chip                                        PAD_NET and chip_blocks() below: pads to nets (pins.csv),
                                              control outputs to block inputs; ro_in[3] to VSS and
                                              ro_en[3] open (the FO4 RO is not built)

Device parameters are compared exactly (to 1 nm, as the deck's TRACE PROPERTY ... 0); parallel MOS are
combined on both sides first (LVS REDUCE PARALLEL MOS YES; KLayout does not reduce series MOS or split
gates and does combine parallel capacitors, which can only add mismatches here). After the comparison
the pins on every matched net must carry the same names on both sides, and the PIP's top plate must
be on ND1 (capacitor pins are swappable in the comparison, as in the deck).
chip_lvs_selftest.py puts errors into the layout or the reference and expects each to mismatch.

usage: python3 designs/etri050/chip/chip_lvs.py [--gds build/pdkv_Top.gds] [--spice out.spice]
       exit 0 on a match; writes build/pdkv_core_lvs.lvsdb (KLayout netlist browser) and, with
       --spice, the extracted netlist as drawn (every finger; nets named after the reference on a match)
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

HERE = Path(__file__).resolve().parent
ETRI = HERE.parent
REPO = ETRI.parents[1]
sys.path.insert(0, str(ETRI / "gen"))
sys.path.insert(0, str(ETRI / "cbcm"))
import etri050_ro as ro  # noqa: E402
import etri050_cbcm as cbgen  # noqa: E402

LAYERS = {"nwell": 2, "act": 11, "poly1": 12, "poly2": 13, "nsd": 14, "psd": 15, "phri": 21, "cont": 31,
          "m1": 32, "v1": 33, "m2": 34, "v2": 35, "m3": 36, "res": 51, "cap": 53, "bjt": 56, "diode": 57,
          "lvsd": 60}
RSH_P2 = 125.0                 # PDK p2res_i RSH, ohm/sq (R reported, W and L compared)
PIP_CAP = 0.5                  # fF/um2, rule document 5.4 typ; only for the reported C
SCH = {"karray": ETRI / "array/build/sch/karray.spice", "cbcm": ETRI / "cbcm/build/sch/cbcm.spice",
       "robank": ETRI / "ro/build/sch/robank.spice", "rores": ETRI / "ro/build/sch/rores.spice",
       "lsplit": ETRI / "direct/build/sch/lsplit.spice", "mosc": ETRI / "direct/build/sch/mosc.spice"}
PINFILES = {"karray": ETRI / "array/build/karray_pins.json", "cbcm": ETRI / "cbcm/build/cbcm_pins.json"}
MACRO_SPC = ETRI / "ctrl/macro/teg_ctrl.spc"
HEATER_WL = (20.0, 120.0)      # pdk_cells.py defaults, the heater in the chip
PIP_WL = (30.0, 30.0)          # etri050_cbcm.py STRUCTURES[1] "PIP 30x30"
PIP_PLATES = ("ND1", "VSS")    # cbcm nets of the PIP's top (POLY2) and bottom (POLY1) plates
PNP_AE = 100.0                 # pnp10: emitter 10 x 10 um
PNP_EMITTERS = (4.0, 25.0, 100.0)   # um2, the deck's PNPBJT_E_2x2 / 5x5 / 10x10
FORCE_W = 9.0                  # um, force and heater lines at their PAD ports (assemble.py)

# ---- the chip's circuit -------------------------------------------------------------------------
# pad pin (pins.csv) -> chip net. Force and sense pads of one node are one net in the core.
PAD_NET = {"PVDD": "VDD", "PVSS": "VSS", "ASF": "SRC", "ASS": "SRC", "LD1F": "D1", "LD1S": "D1",
           "LSF": "S", "LSS": "S", "LD2F": "D2", "LD2S": "D2"}


def chip_blocks():
    """(instance, circuit, {port: chip net}) for every block; ports not listed stay unconnected."""
    ctrl = {"vdd": "VDD", "gnd": "VSS", "sck": "SCK", "sdi": "SDI", "sle": "SLE", "cck": "CCK", "out": "OUT",
            "cbcm_clk": "CBCM_CLK", "ro_in[3]": "VSS"}            # FO4 RO not built: input tied low
    ctrl.update({f"row_sel[{i}]": f"ROW_SEL{i}" for i in range(12)})
    ctrl.update({f"row_selb[{i}]": f"ROW_SELB{i}" for i in range(12)})
    ctrl.update({f"col_sel[{i}]": f"COL_SEL{i}" for i in range(8)})
    ctrl.update({f"col_selb[{i}]": f"COL_SELB{i}" for i in range(8)})
    ctrl.update({f"cbcm_en[{i}]": f"CBCM_EN{i}" for i in range(10)})
    ctrl.update({f"ro_en[{i}]": f"RO_EN{i}" for i in (0, 1, 2, 4, 5)})   # ro_en[3] open
    ctrl.update({f"ro_in[{i}]": f"RO_IN{i}" for i in (0, 1, 2, 4, 5)})
    karray = {p: p for p in ("AG", "ADF", "ADS", "SRC", "ANW", "VDD", "VSS")}
    karray.update({f"col_sel{i}": f"COL_SEL{i}" for i in range(8)})
    karray.update({f"col_selb{i}": f"COL_SELB{i}" for i in range(8)})
    karray.update({f"row_sel{i}": f"ROW_SEL{i}" for i in range(12)})
    karray.update({f"row_selb{i}": f"ROW_SELB{i}" for i in range(12)})
    cbcm = {"clk": "CBCM_CLK", "VCD": "VCD", "VCR": "VCR", "VDD": "VDD", "VSS": "VSS"}
    cbcm.update({f"en{i}": f"CBCM_EN{i}" for i in range(10)})
    robank = {"VDD": "VDD", "VSS": "VSS"}
    robank.update({f"en{i}": f"RO_EN{i}" for i in (0, 1, 2, 4)})
    robank.update({f"in{i}": f"RO_IN{i}" for i in (0, 1, 2, 4)})
    rores = {"en5": "RO_EN5", "in5": "RO_IN5", "VDD": "VDD", "VSS": "VSS"}
    return [("ctrl", "teg_ctrl", ctrl), ("array", "karray", karray), ("cbcm", "cbcm", cbcm),
            ("robank", "robank", robank), ("rores", "rores", rores),
            ("lsplit", "lsplit", {"LG": "LG", "LD1F": "D1", "LSF": "S", "LD2F": "D2", "VSS": "VSS"}),
            ("mosc", "mosc", {"CHI": "CHI", "CLO": "CLO"}),
            ("pnp1", "pnp10", {"E": "PE1", "B": "VSS", "C": "VSS"}),
            ("pnp2", "pnp10", {"E": "PE2", "B": "VSS", "C": "VSS"}),
            ("heater", "heater", {"A": "HT", "B": "VSS"})]


def pad_pins():
    """[(pin name, chip net, pad, port rect um, port kind)] in pad order; two PVDD pads: PVDD_W1, PVDD_S7."""
    rows = list(csv.DictReader(open(HERE / "pins.csv", encoding="utf-8")))
    rects = {p["pad"]: p for p in json.load(open(HERE / "build/pad_pins.json"))["pads"]}
    count = collections.Counter(r["pin"] for r in rows)
    out = []
    for r in rows:
        p = rects[r["pad"]]
        if p["pin"] != r["pin"]:
            raise SystemExit(f"pad {r['pad']}: pins.csv {r['pin']}, pad_pins.json {p['pin']}")
        name = r["pin"] if count[r["pin"]] == 1 else f"{r['pin']}_{r['pad']}"
        out.append((name, PAD_NET.get(r["pin"], r["pin"]), r["pad"], p["rect"], r["port"]))
    return out


# block ports anchored as pins: (instance in chip_blocks, cell in the GDS, ports)
ANCHOR_PORTS = [("array", "karray", [f"{s}{i}" for s in ("row_sel", "row_selb") for i in range(12)]
                 + [f"{s}{i}" for s in ("col_sel", "col_selb") for i in range(8)]),
                ("cbcm", "cbcm", [f"en{i}" for i in range(10)])]


def cbcm_nodes():
    """[(cell i, metal layer, block point um)]: a generator rectangle of ND<i> inside cell i's structure
    window (cbcm_c.body_windows; the empty cell 0: its pseudo-inverter pair). Cells 8 and 9 (gates) have
    devices of their own and no metal of ND<i> in the window."""
    import cbcm_c
    blk = cbgen.build()[0]
    win = cbcm_c.body_windows()
    lam = cbgen.LAMBDA_UM
    out = []
    for i in range(cbgen.NCELL):
        w = win.get(i) or cbcm_c.band_window(i)
        for net, lay, x0, y0, x1, y1 in blk.netrects:
            cx, cy = (x0 + x1) / 2 * lam, (y0 + y1) / 2 * lam
            if net == f"ND{i}" and lay in ("metal1", "metal2", "metal3") and w[0] <= cx <= w[2] and w[1] <= cy <= w[3]:
                out.append((i, {"metal1": "m1", "metal2": "m2", "metal3": "m3"}[lay], (cx, cy)))
                break
    return out


def anchors(placement):
    """[(pin name, reference instance, reference port or internal net, layer, die point)] for the layout and
    the reference. placement: GDS cell name -> its instance transformation in the chip (um)."""
    out = []
    for inst, cell, ports in ANCHOR_PORTS:
        pins = json.load(open(PINFILES[cell]))["pins"]
        t = placement[cell]
        for port in ports:
            p = pins[port]
            x0, y0, x1, y1 = p["box"]
            at = t * kdb.DPoint((x0 + x1) / 2, (y0 + y1) / 2)
            out.append((f"{inst}:{port}", inst, ("port", port), {"metal1": "m1", "metal2": "m2", "metal3": "m3"}[p["layer"]], at))
    t = placement["cbcm"]
    for i, lay, (x, y) in cbcm_nodes():
        out.append((f"cbcm:ND{i}", "cbcm", ("net", f"ND{i}"), lay, t * kdb.DPoint(x, y)))
    return out


# ---- the pad ring --------------------------------------------------------------------------------
def ring_groups(gds: Path, pins):
    """Core ports the pad ring itself joins: the pdkv_Pad placed in this GDS, its metal flattened and
    probed on metal2 at each port. Returns [[pin names]] for groups of two or more."""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    for inst in list(top.each_inst()):
        if inst.cell.name != "pdkv_Pad":
            inst.delete()
    for li in ly.layer_indexes():
        top.shapes(li).clear()
    ly.flatten(top.cell_index(), -1, True)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, top, []))
    M = {k: l2n.make_layer(ly.layer(n, 0), k) for k, n in
         (("m1", 32), ("v1", 33), ("m2", 34), ("v2", 35), ("m3", 36), ("pad", 37))}
    for r in M.values():
        l2n.connect(r)
    for a, b in (("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3"), ("m3", "pad")):
        l2n.connect(M[a], M[b])
    l2n.extract_netlist()
    owner = collections.defaultdict(set)
    for name, _, pad, (x1, y1, x2, y2), _ in pins:
        nets = set()
        for f in (0.1, 0.3, 0.5, 0.7, 0.9):
            pt = (kdb.DPoint((x1 + x2) / 2, y1 + f * (y2 - y1)) if x2 - x1 < y2 - y1
                  else kdb.DPoint(x1 + f * (x2 - x1), (y1 + y2) / 2))
            n = l2n.probe_net(M["m2"], pt)
            nets.add(n.cluster_id if n is not None else None)
        if len(nets) != 1 or None in nets:
            raise SystemExit(f"pad ring: the metal2 port of {pad} ({name}) is not one ring net")
        owner[nets.pop()].add(name)
    return [sorted(g) for g in owner.values() if len(g) > 1]


# ---- reference ----------------------------------------------------------------------------------
def kit_file():
    """The kit's standard-cell netlist (as etri050_cbcm.kit_stdcells_spice finds it)."""
    dk = os.environ.get("ETRI050_DK", str(REPO / ".pdk/ETRI050_DesignKit"))
    if not Path(dk).is_dir():
        dk = str(Path.home() / "ETRI050_DesignKit")
    return Path(dk) / "digital_ETRI/khu_etri050_stdcells.spice"


SUBCKT = re.compile(r"^\.subckt\s+(\S+).*?^\.ends.*?$", re.S | re.M | re.I)


def strip_kit_cells(text, kit, src):
    """Drop the kit cells a block netlist includes, after checking each is the kit's own text."""
    def norm(s):
        return " ".join(s.split()).lower()

    def repl(m):
        name = m.group(1)
        if name in kit:
            if norm(m.group(0)) != norm(kit[name]):
                raise SystemExit(f"{src}: {name} differs from the kit's netlist")
            return ""
        return m.group(0)
    return SUBCKT.sub(repl, text)


def reference_netlist(pins, anchor_list):
    kit_txt = kit_file().read_text()
    kit = {m.group(1): m.group(0) for m in SUBCKT.finditer(kit_txt)}
    parts = [kit_txt, ".subckt FILL gnd vdd\n.ends\n"]            # the kit has no FILL netlist
    for name, path in SCH.items():
        parts.append(strip_kit_cells(path.read_text(), kit, path.name))
    parts.append(MACRO_SPC.read_text())
    parts.append(".subckt pnp10 E B C\n.ends\n.subckt heater A B\n.ends\n")
    with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as f:
        f.write("\n".join(parts))
    ref = kdb.Netlist()
    ref.read(f.name, kdb.NetlistSpiceReader())
    Path(f.name).unlink()

    def circ(name):
        c = ref.circuit_by_name(name.upper()) or ref.circuit_by_name(name)
        if c is None:
            raise SystemExit(f"reference: no circuit {name}")
        return c

    res = kdb.DeviceClassResistor()
    res.name = "P2RES"
    pip = kdb.DeviceClassCapacitor()
    pip.name = "PIP"
    pnp = kdb.DeviceClassBJT3Transistor()
    pnp.name = "PNP"
    for dc in (res, pip, pnp):
        ref.add(dc)

    def pin_net(c, pin):
        for p in c.each_pin():
            if p.name().upper() == pin.upper():
                return c.net_for_pin(p)
        raise SystemExit(f"reference: {c.name} has no pin {pin}")

    def add_res(c, name, a, b, w, l):
        d = c.create_device(res, name)
        for k, v in (("R", RSH_P2 * l / w), ("W", w), ("L", l), ("A", w * l), ("P", 2 * (w + l))):
            d.set_parameter(k, v)
        d.connect_terminal("A", a)
        d.connect_terminal("B", b)

    # rores: each p2r40 head pair is one P2RES W 2 x L 80
    p2 = circ("p2r40")
    add_res(p2, "R", pin_net(p2, "A"), pin_net(p2, "B"), ro.R_W_UM, ro.R_L_UM)
    h = circ("heater")
    add_res(h, "R", pin_net(h, "A"), pin_net(h, "B"), *HEATER_WL)
    q = circ("pnp10")
    d = q.create_device(pnp, "Q")
    d.set_parameter("AE", PNP_AE)
    d.set_parameter("NE", 1)
    for t in "EBC":
        d.connect_terminal(t, pin_net(q, t))
    c = circ("cbcm")
    top_plate, bottom_plate = (c.net_by_name(n) for n in PIP_PLATES)
    if top_plate is None or bottom_plate is None:
        raise SystemExit(f"reference: cbcm has no {PIP_PLATES} nets for the PIP")
    d = c.create_device(pip, "PIP")
    w, l = PIP_WL
    for k, v in (("C", PIP_CAP * w * l * 1e-15), ("A", w * l), ("P", 2 * (w + l))):
        d.set_parameter(k, v)
    d.connect_terminal("A", top_plate)
    d.connect_terminal("B", bottom_plate)

    top = kdb.Circuit()
    top.name = "PDKV_CORE"
    ref.add(top)
    nets = {}

    def net(n):
        if n not in nets:
            nets[n] = top.create_net(n)
        return nets[n]
    for name, chip_net, _, _, _ in pins:
        top.connect_pin(top.create_pin(name), net(chip_net))
    port_net = {}
    for inst, cname, conn in chip_blocks():
        cc = circ(cname)
        sc = top.create_subcircuit(cc, inst)
        ports = {p.name().upper(): p for p in cc.each_pin()}
        for port, chip_net in conn.items():
            if port.upper() not in ports:
                raise SystemExit(f"reference: {cname} has no port {port}")
            sc.connect_pin(ports[port.upper()], net(chip_net))
            port_net[(inst, port.upper())] = net(chip_net)
        for port, p in ports.items():               # an open port keeps its net inside the block
            if port not in {k.upper() for k in conn}:
                sc.connect_pin(p, net(f"{inst}.{port}"))
                port_net[(inst, port)] = net(f"{inst}.{port}")
    for c in [c for c in ref.each_circuit() if c.name != top.name]:
        ref.flatten_circuit(c)
    by_name = {n.name.upper(): n for n in top.each_net()}       # (net_by_name misses flattened nets)
    for name, inst, (kind, what), _, _ in anchor_list:
        n = port_net.get((inst, what.upper())) if kind == "port" else by_name.get(f"{inst}.{what}".upper())
        if n is None:
            raise SystemExit(f"reference: no net for the anchor {name}")
        top.connect_pin(top.create_pin(name), n)
    return ref, top


# ---- layout -------------------------------------------------------------------------------------
def core_layout(gds: Path):
    """The chip without pad ring and seal, flattened; returns (layout, top, {cell: placement (um)})."""
    ly = kdb.Layout()
    ly.read(str(gds))
    top = ly.top_cell()
    gone, placement = [], {}
    for inst in list(top.each_inst()):
        if inst.cell.name in ("pdkv_Pad", "pdkv_SEAL"):
            gone.append(inst.cell.name)
            inst.delete()
        else:
            placement.setdefault(inst.cell.name, inst.dcplx_trans)
    if sorted(gone) not in (["pdkv_Pad", "pdkv_SEAL"], ["pdkv_Pad"]):
        raise SystemExit(f"{gds}: pad ring / seal instances {gone}")
    ly.flatten(top.cell_index(), -1, True)
    return ly, top, placement


def extract(ly, top, pins, groups=(), anchor_list=()):
    sub = ly.layer(999, 0)                                   # substrate helper, in memory only
    top.shapes(sub).insert(top.bbox().enlarged(10000))
    port = ly.layer(998, 0)                                  # pad cell port metal (see the docstring)
    joined = [ly.layer(990 + k, 0) for k in range(len(groups))]   # ports the ring joins, a layer each
    for name, _, _, r, _ in pins:
        k = [k for k, g in enumerate(groups) if name in g]
        top.shapes(joined[k[0]] if k else port).insert(kdb.DBox(*r).to_itype(ly.dbu))
    lv = kdb.LayoutVsSchematic(kdb.RecursiveShapeIterator(ly, top, []))
    L = {k: lv.make_layer(ly.layer(n, 0), k) for k, n in LAYERS.items()}
    L["sub"] = lv.make_layer(sub, "sub")
    L["port"] = lv.make_layer(port, "port")
    L["ring"] = [lv.make_layer(j, f"ring{k}") for k, j in enumerate(joined)]
    ext = L["cap"] | L["bjt"] | L["diode"]                   # EXTLAYER
    nact = (L["act"] & L["nsd"]) - ext
    pact = (L["act"] & L["psd"]) - ext
    ngate = (nact & L["poly1"]) - L["nwell"]
    pgate = (pact & L["poly1"]) & L["nwell"]
    nisd = (nact - ngate).interacting(ngate)
    pisd = (pact - pgate).interacting(pgate)
    ntap = (nact & L["nwell"]).not_interacting(L["poly1"])
    ptap = (pact - L["nwell"]).not_interacting(L["poly1"])
    bulk = L["sub"] - L["nwell"]
    pl1 = L["poly1"] - L["cap"]                              # PL1_NOT_CAP
    # P2RES
    body = L["poly2"] & ((L["lvsd"] & L["res"]).not_interacting(L["phri"]))
    rterm = L["poly2"].interacting(body) - L["lvsd"]
    # PIPCAP
    pipcap = L["nsd"] & L["cap"]
    pip_pl1 = L["poly1"].interacting(pipcap)
    pip_pl2 = L["poly2"].interacting(pipcap)
    pip_pos = pip_pl2 & pip_pl1
    pip_neg = pip_pl1 ^ pip_pl2
    # PNP
    um2 = 1.0 / (ly.dbu * ly.dbu)
    bjt_nw = L["bjt"] & L["nwell"]
    bact = L["act"] & L["bjt"]
    pbact, nbact = bact & L["psd"], bact & L["nsd"]
    pnp_e_base = pbact & bjt_nw
    pnp_e = None
    for a in PNP_EMITTERS:
        r = pnp_e_base.with_area(int((a - 0.001) * um2), int((a + 0.001) * um2), False)
        pnp_e = r if pnp_e is None else pnp_e + r
    pnp_b_base = bjt_nw.interacting(pnp_e)
    pnp_bc = (bjt_nw & nbact).inside(pnp_b_base)
    ring = pbact - bjt_nw
    pnp_c_base = ring.holes().interacting(pnp_e)
    pnp_c = ring.with_holes(1, None, False).interacting(pnp_c_base)
    pnp_dev = (pnp_c_base | pnp_c) & L["bjt"]                # PBJT, the device region
    for name, reg in (("ngate", ngate), ("pgate", pgate), ("nisd", nisd), ("pisd", pisd), ("ntap", ntap),
                      ("ptap", ptap), ("bulk", bulk), ("pl1", pl1), ("r_body", body), ("r_term", rterm),
                      ("pip_pl1", pip_pl1), ("pip_pos", pip_pos), ("pip_neg", pip_neg), ("pnp_e", pnp_e),
                      ("pnp_bc", pnp_bc), ("pnp_c", pnp_c), ("pnp_dev", pnp_dev)):
        lv.register(reg, name)
    lv.extract_devices(kdb.DeviceExtractorMOS4Transistor("NFET"), {"SD": nisd, "G": ngate, "P": pl1, "W": bulk})
    lv.extract_devices(kdb.DeviceExtractorMOS4Transistor("PFET"), {"SD": pisd, "G": pgate, "P": pl1, "W": L["nwell"]})
    lv.extract_devices(kdb.DeviceExtractorResistor("P2RES", RSH_P2), {"R": body, "C": rterm})
    lv.extract_devices(kdb.DeviceExtractorCapacitor("PIP", PIP_CAP * 1e-15), {"P1": pip_pos, "P2": pip_pl1,
                                                                           "tA": pip_pos, "tB": pip_pl1})
    lv.extract_devices(kdb.DeviceExtractorBJT3Transistor("PNP"), {"B": pnp_dev, "E": pnp_e, "C": pnp_c,
                                                                 "tB": pnp_dev, "tE": pnp_e, "tC": pnp_c})
    for reg in (pl1, rterm, nisd, pisd, ntap, ptap, L["nwell"], bulk, pip_pos, pip_neg, pnp_e, pnp_bc, pnp_c,
                L["cont"], L["m1"], L["v1"], L["m2"], L["v2"], L["m3"], L["port"]):
        lv.connect(reg)
    for reg in (pl1, rterm, nisd, pisd, ntap, ptap, pip_pos, pip_neg, pnp_e, pnp_bc, pnp_c):
        lv.connect(L["cont"], reg)
    for a, b in (("cont", "m1"), ("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3")):
        lv.connect(L[a], L[b])
    lv.connect(L["port"], L["m2"])                           # the GPIO ports are metal2
    for k, j in enumerate(L["ring"]):
        lv.connect(j)
        lv.connect(j, L["m2"])
        lv.connect_global(j, f"PAD_RING_{k}")
    lv.soft_connect(ntap, L["nwell"])                        # SCONNECT NTAP NWELL
    lv.soft_connect(ptap, bulk)                              # SCONNECT PTAP PWELL
    lv.soft_connect(pnp_bc, L["nwell"])                      # the PNP base well, reached by its n+
    lv.connect(pnp_dev)
    lv.connect(pip_pl1)
    lv.connect(pnp_dev, pnp_bc)                              # base terminal = the base contact's net
    lv.connect(pip_pl1, pip_neg)                             # bottom plate terminal to PIP_NEG
    lv.connect(pip_pl1, pl1)                                 # POLY1 is one conductor across CAP
    lv.connect_global(bulk, "SUBSTRATE")
    lv.extract_netlist()
    # what the layout draws as a device, whether or not it was recognized as one
    L["drawn"] = {"MOS": (L["act"] & L["poly1"]).count(), "P2RES": (L["poly2"] & L["lvsd"] & L["res"]).count(),
                  "PIP": pipcap.count(), "PNP": L["bjt"].count(), "DIODE": L["diode"].count(),
                  "POLY2 off devices": L["poly2"].not_interacting(body).not_interacting(pipcap).count()}
    # the deck's PIP W and L, and malformed PIPs
    pip_wl = []
    for p in pipcap.each():
        cell = kdb.Region(p)
        w = (cell & L["lvsd"]).area() / um2 / 0.2
        a = (pip_pos & cell).area() / um2
        pip_wl.append((round(w, 3), round(a / w, 3) if w else 0.0))
    L["pip_wl"] = sorted(pip_wl)
    L["pip_poly2_out"] = (pip_pl2 - pip_pl1).count()
    L["m2_flat"] = L["m2"]
    return lv, L


def name_pins(lv, L, pins, anchor_list):
    """Pins at the pad ports and at the anchors; returns (top circuit, problems)."""
    circ = next(lv.netlist().each_circuit_top_down())
    problems = []
    m2 = L["m2_flat"]
    for name, chip_net, pad, r, kind in pins:
        x1, y1, x2, y2 = r
        box = kdb.DBox(*r)
        core = m2 & kdb.Region(box.to_itype(lv.internal_layout().dbu))
        if core.is_empty():
            problems.append(f"pad {pad} ({name}): no core metal2 at the port")
        elif kind == "PAD":                                  # force / heater port: the 9 um line
            bb = core.bbox().to_dtype(lv.internal_layout().dbu)
            span = bb.height() if x2 - x1 < y2 - y1 else bb.width()
            if span < FORCE_W - 0.001:
                problems.append(f"pad {pad} ({name}): a {span:g} um line at a force port ({FORCE_W:g} um expected)")
        at = kdb.DPoint((x1 + x2) / 2, (y1 + y2) / 2)
        net = None
        for layer in [L["port"]] + L["ring"]:
            net = net or lv.probe_net(layer, at)
        if net is None:
            problems.append(f"pad {pad} ({name}): no port")
            continue
        net.name = chip_net
        circ.connect_pin(circ.create_pin(name), net)
    for name, inst, what, lay, at in anchor_list:
        net = lv.probe_net(L[lay], at)
        if net is None:
            problems.append(f"anchor {name}: no {lay} at {at}")
            continue
        circ.connect_pin(circ.create_pin(name), net)
    return circ, problems


TOL = {"NFET": ("W", "L"), "PFET": ("W", "L"), "P2RES": ("W", "L"), "PIP": ("A", "P"), "PNP": ("AE",)}


def compare_settings(netlist):
    """Compare the deck's traced properties exactly (1 nm / 0.001 um2 for rounding), nothing else."""
    for dc in netlist.each_device_class():
        names = TOL.get(dc.name)
        if not names:
            continue
        eq = None
        for n in names:
            e = kdb.EqualDeviceParameters(dc.parameter_id(n), 0.001, 0.0)
            eq = e if eq is None else eq + e
        dc.equal_parameters = eq


def lvs(gds: Path, lvsdb: Path = None, spice: Path = None, named=False):
    """-> (match, report lines), or with named=True (match, report lines, netlist): the extracted netlist
    as drawn (parallel devices not combined), its nets named after their reference nets on a match"""
    pins = pad_pins()
    groups = ring_groups(gds, pins)
    ly, top, placement = core_layout(gds)
    anchor_list = anchors(placement)
    lv, L = extract(ly, top, pins, groups, anchor_list)
    circ, problems = name_pins(lv, L, pins, anchor_list)
    for e in lv.each_log_entry():                             # soft connections joining separate nets
        problems.append(f"extraction {str(e.severity).lower()}: {e.message}"[:240])
    lnl = lv.netlist()
    lnl.flatten()
    raw = collections.Counter(d.device_class().name for d in circ.each_device())
    found = {"MOS": raw["NFET"] + raw["PFET"], "P2RES": raw["P2RES"], "PIP": raw["PIP"], "PNP": raw["PNP"],
             "DIODE": 0, "POLY2 off devices": 0}
    for k, n in L["drawn"].items():
        if found[k] != n:
            problems.append(f"{k}: {n} drawn, {found[k]} recognized")
    if L["pip_wl"] != [PIP_WL]:
        problems.append(f"PIP W x L as the deck computes them {L['pip_wl']}, design {[PIP_WL]}")
    if L["pip_poly2_out"]:
        problems.append(f"{L['pip_poly2_out']} PIP POLY2 shapes beyond their POLY1")
    drawn = lnl.dup()                                         # for simulation: every finger as drawn
    ref, rtop = reference_netlist(pins, anchor_list)
    lnl.combine_devices()
    ref.combine_devices()
    lnl.purge_nets()
    ref.purge_nets()
    compare_settings(lnl)
    compare_settings(ref)
    lv.reference = ref
    cmp = kdb.NetlistComparer()
    cmp.same_circuits(circ, rtop)
    ok = lv.compare(cmp)
    rep = []
    lay_cnt = collections.Counter(d.device_class().name for d in circ.each_device())
    ref_cnt = collections.Counter(d.device_class().name for d in rtop.each_device())
    xref = lv.xref()
    st = collections.Counter()
    good_status = (kdb.NetlistCrossReference.Match, kdb.NetlistCrossReference.MatchWithWarning)
    bad_nets, bad_devs, bad_pins, pin_names = [], [], [], []
    pinned = {}
    for cp in xref.each_circuit_pair():
        for n in xref.each_net_pair(cp):
            st["net " + str(n.status())] += 1
            a, b = n.first(), n.second()
            if n.status() not in good_status or a is None or b is None:
                bad_nets.append((a.expanded_name() if a else "-", b.expanded_name() if b else "-", str(n.status())))
                continue
            # pins are compared by net: the pins on a net (two for a force + sense pair, both PVDD pads,
            # the anchors) must carry the same names on both sides; KLayout pairs one pin per net itself
            pa = sorted(p.pin().name().upper() for p in a.each_pin())
            pb = sorted(p.pin().name().upper() for p in b.each_pin())
            if pa or pb:
                pinned[b.expanded_name()] = pa
                if pa != pb:
                    pin_names.append((a.expanded_name(), "+".join(pa) or "-", "+".join(pb) or "-"))
        for d in xref.each_device_pair(cp):
            st["device " + str(d.status())] += 1
            if d.status() not in good_status or d.first() is None or d.second() is None:
                bad_devs.append((d.first().expanded_name() if d.first() else "-",
                                 d.second().expanded_name() if d.second() else "-", str(d.status())))
        for p in xref.each_pin_pair(cp):
            if p.status() not in good_status:
                a, b = p.first(), p.second()
                bad_pins.append((a.name() if a else "-", b.name() if b else "-", str(p.status())))
    n_pinned = sum(len(v) for v in pinned.values())
    if n_pinned != len(pins) + len(anchor_list):
        problems.append(f"{n_pinned} of {len(pins) + len(anchor_list)} pins on matched nets")
    # the PIP's plates are swappable for the comparison (LVS ALL CAPACITOR PINS SWAPPABLE YES); the
    # design wants the top plate (POLY2) on the node and the bottom plate (POLY1) on VSS: check that apart
    for cp in xref.each_circuit_pair():
        for d in xref.each_device_pair(cp):
            a, b = d.first(), d.second()
            if a is not None and b is not None and a.device_class().name == "PIP":
                top_l, top_r = a.net_for_terminal(0), b.net_for_terminal(0)
                other = xref.other_net_for(top_l) if top_l is not None else None
                if other is None or top_r is None or other.expanded_name() != top_r.expanded_name():
                    problems.append(f"PIP {a.expanded_name()}: top plate on {top_l.expanded_name() if top_l else '-'},"
                                    f" reference top plate on {top_r.expanded_name() if top_r else '-'}")
    rep.append(f"layout {gds.name} without pad ring and seal: " + ", ".join(f"{k} {v}" for k, v in sorted(raw.items()))
               + "; drawn: " + ", ".join(f"{k} {v}" for k, v in L["drawn"].items())
               + f"; PIP W x L {L['pip_wl']}")
    rep.append("after combining parallel devices, layout: " + ", ".join(f"{k} {v}" for k, v in sorted(lay_cnt.items())))
    rep.append("after combining parallel devices, reference: " + ", ".join(f"{k} {v}" for k, v in sorted(ref_cnt.items())))
    rep.append(f"pins: {len(pins)} at the pad cells' core ports (metal2; joined by the pad ring: "
               + (", ".join(" + ".join(g) for g in groups) or "none") + f"), {len(anchor_list)} anchors"
               + ("; problems: " + "; ".join(problems) if problems else "; soft connections clean"))
    rep.append("cross reference: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))
    rep.append(f"pins by net: {len(pinned)} matched nets carry the {n_pinned} pins with the same names on both sides"
               if not pin_names else "pins by net: names differ")
    for title, rows in (("unmatched nets", bad_nets), ("unmatched devices", bad_devs), ("unmatched pins", bad_pins),
                        ("nets whose pins differ (layout net, layout pins, reference pins)", pin_names)):
        if rows:
            rep.append(f"{title}: {len(rows)}")
            rep += ["  " + " <-> ".join(map(str, r)) for r in rows[:25]]
    good = ok and not problems and not bad_pins and not pin_names and lay_cnt == ref_cnt
    rep.append("chip core LVS: " + ("MATCH" if good else "MISMATCH"))
    if lvsdb:
        lvsdb.parent.mkdir(parents=True, exist_ok=True)
        lv.write(str(lvsdb))
    if good:                                                  # name the drawn nets after the reference
        name = {}
        for cp in xref.each_circuit_pair():
            for n in xref.each_net_pair(cp):
                name[n.first().cluster_id] = n.second().expanded_name()
        dtop = drawn.circuit_by_name(circ.name)
        for n in dtop.each_net():
            if n.cluster_id in name:
                n.name = name[n.cluster_id]
    if spice:
        w = kdb.NetlistSpiceWriter()
        w.use_net_names = True
        drawn.write(str(spice), w, f"pdkv core extracted from {gds.name} ({'nets named after the reference' if good else 'no match'})")
    return (good, rep, drawn) if named else (good, rep)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gds", type=Path, default=HERE / "build/pdkv_Top.gds")
    ap.add_argument("--lvsdb", type=Path, default=HERE / "build/pdkv_core_lvs.lvsdb")
    ap.add_argument("--spice", type=Path)
    args = ap.parse_args(argv)
    ok, rep = lvs(args.gds, args.lvsdb, args.spice)
    print("\n".join(rep))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
