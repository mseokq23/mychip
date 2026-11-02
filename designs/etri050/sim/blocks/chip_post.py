"""The whole chip core at transistor level, as drawn: the netlist chip_lvs.py extracts from pdkv_Top.gds
(every device as drawn, nets named after the reference after a match), simulated with the PDK models.

The pad ring is cut at the pad cells' core ports as in the LVS: pads are sources at those ports (SCK,
SDI, SLE, CCK are the PIC outputs, OUT drives 0.1 pF for the POB4 input), so nothing here depends on
ETRI's GPIO cells. A pad that carries no DC current is driven through R_PAD. No wiring parasitics:
devices only (junction areas and perimeters as extracted). The drawn wiring of the array, CBCM and RO
blocks was simulated block by block (array_post, cbcm_post, ro_post); the control block's wiring is
simulated nowhere (its qflow STA is no sign-off), so the scan corners show function, not timing margin.

  scan     five 20-bit frames through SDI / SCK / SLE at 10 MHz: mode 01 (NMOS row 2 col 0, then PMOS
           row 9 col 1), 00, 10 (CBCM cell 9, CCK still), 11 (RO 5, osel 0). Every select and enable
           line is compared with the register map (ctrl/README.md) after each SLE and again halfway
           through the next frame's shift (the shadow register must hold); while a frame shifts in, OUT
           must show the one before bit by bit (read-back, osel = 0). TT 27 C, SS 125 C 4.5 V, FF 27 C
           5.5 V
  array    frames 1 and 2: I(ADF) against the same drawn device alone with its gate on AG, its drain at
           the voltage sensed through ADS and its source on SRC (what a measurement assumes); the
           selected row's gate must sit at AG and AG must draw nothing. Frame 3 (mode 00): nothing but
           the simulator's gmin may flow from ADF
  cbcm     cell 1 (PIP) and cell 0 (empty) through CCK at 1 MHz, VCD = VCR = 5 V, then mode 01 with CCK
           running. Cell 1 against the block netlist's reading of the same plate (cbcm_block.py), cell 0
           near 0 but clocked (its pair's charge from VCD), CBCM_CLK toggling in mode 10 and still in
           mode 01, the enable lines as selected
  ro       mode 11, osel = 1. RO 0 (INV): OUT (divide by 256) changes every 128 RO periods, so half an
           OUT period x f(ro_in[0]) must be 128; f(ro_in[0]) against the block netlist without wiring
           (ro_post.py); RO_EN0 the only enable high and the other taps still. RO 3 (FO4, not built, its
           tap tied low): no enable high, every tap, the RO mux and OUT still

The L-split, heater and PNPs are not run here: all their terminals are pads, so once the LVS has
matched the devices a transistor-level run of them cannot fail (lsplit.py and pnp_thermo.py are their
checks).

usage: python3 chip_post.py        (needs designs/etri050/chip/build: run_chip.sh)
"""
from concurrent.futures import ProcessPoolExecutor
import math
import re
import sys
from pathlib import Path

from simlib import header, p2res, run

HERE = Path(__file__).resolve().parent
CHIP = HERE.parents[1] / "chip"
sys.path.insert(0, str(CHIP))

NAN = float("nan")
PER = 100e-9                    # SCK 10 MHz
NBIT = 20
COX, CAPSW = 0.5e-15, 0.09e-15  # PIP: pipcap_i COX (F/um2 here) and CAPSW (F/um); rule document 5.4 typ
OUT_LOAD = 0.1e-12
PIP_C = None                    # the drawn PIP as simulated (COX x area + CAPSW x perimeter), set by chip_netlist()
# A pad source that only charges gates or junctions carries a branch current of nothing but rounding.
# Once the time step gets small at a clock edge, ngspice cannot converge that current and gives up
# ("timestep too small ... trouble with node vlg#branch", 2026-11-02: at 0.30 us or at 2.85 us,
# depending only on the order of the devices in the deck). Such pads are driven through 100 ohm, about
# a pad driver's output, which leaves their DC levels as they are. With it every deck runs through with
# its devices in the order written here and in reverse, to the same results (2026-11-02).
# Pads with DC current (VDD, ADF and SRC in the array frames) stay ideal.
R_PAD = 100.0


def frame(mode=0, row=15, col=0, cbsel=15, rosel=7, osel=0):
    """Register bits [19:0] as an int (ctrl/README.md)."""
    return mode | row << 2 | col << 6 | cbsel << 9 | rosel << 13 | osel << 16


def sanitize(names):
    out, used = {}, set()
    for n in names:
        s = re.sub(r"[^A-Za-z0-9_]", "_", n)
        if s in used:
            k = 2
            while f"{s}_{k}" in used:
                k += 1
            s = f"{s}_{k}"
        used.add(s)
        out[n] = s
    out["VSS"] = "0"
    return out


_NET = {}


def chip_netlist():
    """(device lines with temperature placeholders, net name map, device list) from the LVS."""
    if _NET:
        return _NET["lines"], _NET["names"], _NET["devs"]
    import chip_lvs
    ok, rep, nl = chip_lvs.lvs(CHIP / "build/pdkv_Top.gds", named=True)
    if not ok:
        raise SystemExit("chip LVS does not match:\n" + "\n".join(rep))
    top = next(nl.each_circuit_top_down())
    names = sanitize([n.expanded_name() for n in top.each_net()])
    # One deck per circuit: the extractor's device order (and which side of a MOS it calls the drain)
    # changes with the KLayout run, and with it the matrix order and the rounding in ngspice. So the
    # devices are written in a fixed order, a MOS with its drain the lower net name.
    recs = []
    for d in top.each_device():
        cls = d.device_class().name
        t = {td.name: names[d.net_for_terminal(td.id()).expanded_name()] for td in d.device_class().terminal_definitions()}
        p = {pd.name: d.parameter(pd.name) for pd in d.device_class().parameter_definitions()}
        if cls in ("NFET", "PFET") and t["S"] < t["D"]:
            t = dict(t, D=t["S"], S=t["D"])
            p = dict(p, AD=p["AS"], AS=p["AD"], PD=p["PS"], PS=p["PD"])
        if cls == "P2RES" and t["B"] < t["A"]:
            t = dict(t, A=t["B"], B=t["A"])
        recs.append((cls, t, p))
    recs.sort(key=lambda r: (r[0], sorted(r[1].items()), sorted(r[2].items())))
    lines, devs = [], []
    for k, (cls, t, p) in enumerate(recs):
        if cls in ("NFET", "PFET"):
            model = "nmos4" if cls == "NFET" else "pmos4"
            line = (f"M{k} {t['D']} {t['G']} {t['S']} {t['B']} {model} w={p['W']:.4g}u l={p['L']:.4g}u "
                    f"ad={p['AD']:.4g}p as={p['AS']:.4g}p pd={p['PD']:.4g}u ps={p['PS']:.4g}u")
        elif cls == "P2RES":
            line = f"R{k} {t['A']} {t['B']} {{R_SQ*{p['L'] / p['W']:.6g}}}"
        elif cls == "PIP":
            global PIP_C
            PIP_C = COX * p['A'] + CAPSW * p['P']
            line = f"C{k} {t['A']} {t['B']} {PIP_C:.6g}"
        elif cls == "PNP":
            line = f"Q{k} {t['C']} {t['B']} {t['E']} pnp10"
        else:
            raise SystemExit(f"no model for {cls}")
        lines.append(line)
        devs.append((cls, t, p, line))
    _NET.update(lines=lines, names=names, devs=devs)
    return lines, names, devs


def net(names, s):
    """The deck's name for a chip net, given as named in the deck (inner nets: block_net)."""
    if s not in set(names.values()):
        raise SystemExit(f"no net {s} in the chip netlist")
    return s


def find_device(devs, cls, **terms):
    """The one device of a class on these nets; a MOS's source and drain may be either way round.
    Returns (class, terminals, parameters, line) with D / S as asked."""
    def fits(t):
        if cls in ("NFET", "PFET") and "D" in terms and "S" in terms:
            rest = {k: v for k, v in terms.items() if k not in "DS"}
            return {t["D"], t["S"]} == {terms["D"], terms["S"]} and all(t[k] == v for k, v in rest.items())
        return all(t[k] == v for k, v in terms.items())
    hit = [d for d in devs if d[0] == cls and fits(d[1])]
    if len(hit) != 1:
        raise SystemExit(f"{len(hit)} {cls} devices with {terms}")
    c, t, p, line = hit[0]
    if cls in ("NFET", "PFET") and "D" in terms and t["D"] != terms["D"]:
        t = dict(t, D=t["S"], S=t["D"])
        p = dict(p, AD=p["AS"], AS=p["AD"], PD=p["PS"], PS=p["PD"])
    return c, t, p, line


def replica(dev, name, **terms):
    """The same drawn MOS alone, its terminals on other nodes."""
    cls, t, p, line = dev
    t = dict(t, **terms)
    model = "nmos4" if cls == "NFET" else "pmos4"
    return (f"{name} {t['D']} {t['G']} {t['S']} {t['B']} {model} w={p['W']:.4g}u l={p['L']:.4g}u "
            f"ad={p['AD']:.4g}p as={p['AS']:.4g}p pd={p['PD']:.4g}u ps={p['PS']:.4g}u")


RAMP = 20e-9                    # supplies and pad voltages ramp up together from 0 (no DC solution
                                # is asked for: a chip full of latches and rings has none worth having)


def wave(v, change=None):
    """A pad waveform ramping with the supply; change = (t, v2) steps it later (10 ns)."""
    pts = f"0 0 {RAMP:.3e} {v}"
    if change:
        t, v2 = change
        pts += f" {t:.6e} {v} {t + 10e-9:.6e} {v2}"
    return f"pwl({pts})"


def src(name, node, v, change=None):
    """An ideal pad source (pads with DC current)."""
    return f"{name} {node} 0 {wave(v, change)}\n"


def pad(name, node, w):
    """A pad without DC current, driven through R_PAD; w is the source's waveform."""
    return f"{name} {node}_drv 0 {w}\nr{name} {node}_drv {node} {R_PAD:g}\n"


def scan_sources(frames, vdd, t0=50e-9, holds=None):
    """SDI / SCK / SLE for frames shifted MSB first, an SLE pulse after each frame and then a hold
    (default 4 SCK periods) before the next. SDI changes a quarter period after SCK falls (25 ns before
    the rising edge that takes it in, 75 ns after the one before) and holds its value until the next
    change, so no source corner falls on a clock edge. Returns (source lines, [(t_sle, t_hold_end)],
    [times of the SCK rising edges])."""
    sck, sdi, sle = ["0 0"], ["0 0"], ["0 0"]
    t = t0
    v = 0.0                                                   # SDI now
    marks, edges = [], []
    for k, f in enumerate(frames):
        for i in range(NBIT - 1, -1, -1):
            b = vdd * ((f >> i) & 1)
            if b != v:
                tc = t + PER / 4
                sdi.append(f"{tc - 1e-9:.6e} {v} {tc + 1e-9:.6e} {b}")
                v = b
            sck.append(f"{t + PER / 2:.6e} 0 {t + PER / 2 + 1e-9:.6e} {vdd} {t + PER - 1e-9:.6e} {vdd} {t + PER:.6e} 0")
            edges.append(t + PER / 2)
            t += PER
        sle.append(f"{t + PER / 4:.6e} 0 {t + PER / 4 + 1e-9:.6e} {vdd} {t + 3 * PER / 4:.6e} {vdd} {t + 3 * PER / 4 + 1e-9:.6e} 0")
        hold = holds[k] if holds else 4 * PER
        marks.append((t + PER / 4, t + hold))
        t += hold
    sdi.append(f"{t:.6e} {v}")
    lines = (pad("vsck", "SCK", f"pwl({' '.join(sck)})") + pad("vsdi", "SDI", f"pwl({' '.join(sdi)})")
             + pad("vsle", "SLE", f"pwl({' '.join(sle)})"))
    return lines, marks, edges


QUIET = (("vag", "AG", 0), ("vadf", "ADF", 0), ("vsrc", "SRC", 0), ("vanw", "ANW", None), ("vchi", "CHI", 0),
         ("vclo", "CLO", 2.5), ("vlg", "LG", 0), ("vd1", "D1", 0), ("vd2", "D2", 0), ("vs", "S", 0),
         ("vht", "HT", 0), ("vvcd", "VCD", 5), ("vvcr", "VCR", 5), ("vcck", "CCK", 0))


def quiet_pads(vdd, skip=()):
    """The pads of the blocks not under test at rest, through R_PAD (ANW at VDD); ADS, PE1, PE2 left
    open (1 Gohm)."""
    x = ""
    for name, node, v in QUIET:
        if node not in skip:
            x += pad(name, node, wave(vdd if v is None else v))
    for node in ("ADS", "PE1", "PE2"):
        if node not in skip:
            x += f"r{node.lower()} {node} 0 1e9\n"
    return x


def lines_for(state):
    """Expected select and enable lines (name -> 0/1) for a register value."""
    mode, row, col = state & 3, state >> 2 & 15, state >> 6 & 7
    cbsel, rosel = state >> 9 & 15, state >> 13 & 7
    e = {}
    for i in range(12):
        on = mode == 1 and row == i
        e[f"ROW_SEL{i}"], e[f"ROW_SELB{i}"] = int(on), int(not on)
    for i in range(8):
        on = mode == 1 and col == i
        e[f"COL_SEL{i}"], e[f"COL_SELB{i}"] = int(on), int(not on)
    for i in range(10):
        e[f"CBCM_EN{i}"] = int(mode == 2 and cbsel == i)
    for i in RO_BUILT:
        e[f"RO_EN{i}"] = int(mode == 3 and rosel == i)
    return e


RO_BUILT = (0, 1, 2, 4, 5)      # RO 3 (FO4) is not on the chip: ro_en[3] open, ro_in[3] tied low


def deck(corner, temp, vdd, extra="", reltol="1e-4", abstol="1e-12", par="", load=None):
    """Gear integration and abstol 1 pA: with the trapezoidal rule or abstol 1 fA the 3000-device
    netlist stops at the first scan edges ('timestep too small' on a quiet pad source's branch).
    par: lines added to the netlist (chip_timing.py: wiring capacitance); load: what OUT drives
    (default OUT_LOAD)."""
    lines, names, devs = chip_netlist()
    body = "\n".join(lines).replace("{R_SQ*", "{RSQ*")
    return (header(corner, temp, reltol=reltol, method="gear", abstol=abstol)
            + ".options gmin=1e-12\n.lib '05cmos_model_260210.lib' BJT\n"
            + f".param RSQ={p2res(temp, 1.0):.6g}\n" + body + "\n" + par
            + src("vdd", "VDD", vdd) + (f"cout OUT 0 {OUT_LOAD}\n" if load is None else load) + extra)


def control(tran, meas, post=""):
    """The .control block: the transient, the measurements [(name, ngspice meas text)] and their values
    echoed as RES lines (50 a line); post: commands after them (chip_timing.py: wrdata)."""
    x = f".control\nset noaskquit\n{tran}\n"
    x += "".join(f"meas tran {k} {m}\n" for k, m in meas)
    keys = [k for k, _ in meas]
    for i in range(0, len(keys), 50):
        x += 'echo "RES ' + " ".join(f"{k}=$&{k}" for k in keys[i:i + 50]) + '"\n'
    return x + post + "quit\n.endc\n.end\n"


def value(r, k):
    """A measured value, NaN when the measurement failed (so a check on it reads CHECK)."""
    v = r.get(k)
    return v if isinstance(v, float) else NAN


def wrong_lines(r, prefix, state, vdd, keys=None):
    """Lines of lines_for(state) (or of keys) that are not at their level, or were not measured."""
    bad = []
    for k, want in lines_for(state).items():
        if keys is not None and k not in keys:
            continue
        v = value(r, f"{prefix}_{k}")
        if math.isnan(v) or (v > vdd / 2) != bool(want):
            bad.append(k)
    return bad


# ---- scan and array -------------------------------------------------------------------------------
F_SCAN = [frame(mode=1, row=2, col=0, cbsel=5, rosel=2),      # NMOS row 2, column 0
          frame(mode=1, row=9, col=1, cbsel=3, rosel=4),      # PMOS row 9, column 1
          frame(mode=0, row=4, col=6, cbsel=9, rosel=1),      # all off
          frame(mode=2, row=7, col=3, cbsel=9, rosel=0),      # CBCM cell 9 (CCK still)
          frame(mode=3, row=11, col=7, cbsel=2, rosel=5)]     # resistor RO (osel 0: OUT stays the scan)
SCAN_CORNERS = (("TT", 27, 5.0), ("SS", 125, 4.5), ("FF", 27, 5.5))
# Everything the scan run measures is settled (levels, DC currents), so reltol 1e-3 is enough: on the
# same circuit and stimulus 1e-3 and 1e-4 gave the same values (NMOS ratio 1.000000, PMOS -0.002 %,
# mode 00 -48 pA, heater 750.00 ohm) in 3 min instead of 9 (TT 27 C, 2026-11-02).
SCAN_RELTOL = "1e-3"


def scan_net(corner, temp, vdd, par="", load=None, post=""):
    lines, names, devs = chip_netlist()
    n = names
    x, marks, edges = scan_sources(F_SCAN, vdd)
    (s1, e1), (s2, e2) = marks[0], marks[1]
    dn = find_device(devs, "NFET", D=n["array.D0"], G=n["array.G2"], S=n["SRC"])
    dp = find_device(devs, "PFET", D=n["array.D1"], G=n["array.G9"], S=n["SRC"])
    sw = (s2 + e1) / 2                                        # array bias change during frame 2's shift
    x += pad("vag", "AG", wave(3.0, (sw, 2.0))) + src("vadf", "ADF", 1.0, (sw, 4.0)) + src("vsrc", "SRC", 0.0, (sw, vdd))
    x += quiet_pads(vdd, skip=("AG", "ADF", "SRC"))
    # replicas: the same drawn device alone as a measurement sees it: gate on AG, drain at the voltage
    # sensed on ADS (a copy, so the sense line carries nothing), source on the forced SRC
    x += "edn dn 0 ADS 0 1\nvmn dn dmn 0\n" + replica(dn, "Mrn", D="dmn", G="AG", S=n["SRC"]) + "\n"
    x += "edp dp 0 ADS 0 1\nvmp dmp dp 0\n" + replica(dp, "Mrp", D="dmp", G="AG", S=n["SRC"]) + "\n"
    meas = []
    keys = list(lines_for(0))
    for k, (s, e) in enumerate(marks):
        tm = e - 0.5 * PER                                    # settled, before the next frame
        meas += [(f"f{k}_{q}", f"find v({n[q]}) at={tm:.6e}") for q in keys]
        meas.append((f"f{k}_iadf", f"find i(vadf) at={tm:.6e}"))
        if k + 1 < len(marks):                                # halfway through the next frame's shift
            th = edges[(k + 1) * NBIT + NBIT // 2] - 2e-9
            meas += [(f"h{k}_{q}", f"find v({n[q]}) at={th:.6e}") for q in keys]
    for k, (g, ammeter) in enumerate((("array.G2", "vmn"), ("array.G9", "vmp"))):
        tm = marks[k][1] - 0.5 * PER
        meas += [(f"f{k}_iref", f"find i({ammeter}) at={tm:.6e}"), (f"f{k}_vg", f"find v({n[g]}) at={tm:.6e}"),
                 (f"f{k}_vag", f"find v(AG) at={tm:.6e}"), (f"f{k}_iag", f"find i(vag) at={tm:.6e}")]
    # OUT while frames 2 ... shift in: the bits of the frame before
    meas += [(f"o{k}", f"find v(OUT) at={te - 2e-9:.6e}") for k, te in enumerate(edges[NBIT:])]
    x += control(f"tran 2n {marks[-1][1] + PER:.6e} 0 2n uic", meas, post)
    return deck(corner, temp, vdd, x, reltol=SCAN_RELTOL, par=par, load=load)


def scan(args):
    corner, temp, vdd = args
    return scan_result(run(scan_net(corner, temp, vdd), f"chip_scan_{corner}_{temp}"), vdd)


def scan_result(r, vdd):
    """What a scan run's measurements show (chip_timing.py reads its runs the same way)."""
    out = {"after": [wrong_lines(r, f"f{k}", f, vdd) for k, f in enumerate(F_SCAN)],
           "mid": [wrong_lines(r, f"h{k}", f, vdd) for k, f in enumerate(F_SCAN[:-1])]}
    want = [(f >> i) & 1 for f in F_SCAN[:-1] for i in range(NBIT - 1, -1, -1)]
    bits = [value(r, f"o{k}") for k in range(len(want))]
    out["readback_bad"] = sum(math.isnan(b) or (b > vdd / 2) != bool(w) for b, w in zip(bits, want))
    out["readback_n"] = len(want)
    out["iadf"] = [value(r, f"f{k}_iadf") for k in range(len(F_SCAN))]
    for q in ("iref", "vg", "vag", "iag"):
        out[q] = [value(r, f"f{k}_{q}") for k in (0, 1)]
    return out


# ---- CBCM -----------------------------------------------------------------------------------------
F_CBCM = [frame(mode=2, cbsel=1), frame(mode=2, cbsel=0), frame(mode=1, row=0, col=0)]
NCK = 6                                                     # CCK periods averaged per frame (1 MHz)
# The charge per period is the small difference of two large ones, so the run needs a tight reltol, as
# cbcm_block.py's accuracy runs (1e-5). Against the drawn plates the chip read cell 1 at -5.4 fF with
# 1e-3 and +2.84 fF with 1e-4 (before R_PAD, when 1e-5 stopped with "timestep too small"); with 1e-5
# it reads +4.75 fF and the block netlist +4.65 fF (2026-11-02).
CBCM_RELTOL = "1e-5"


def cbcm_net(corner, temp, vdd, f_cck=1e6):
    """Each frame is held for NCK + 3 CCK periods; the charge from VCD and VCR is integrated over NCK
    whole periods starting 2 periods after SLE."""
    lines, names, devs = chip_netlist()
    hold = (NCK + 3) / f_cck
    x, marks, edges = scan_sources(F_CBCM, vdd, holds=[hold] * len(F_CBCM))
    windows = []
    for t_sle, t_end in marks:
        start = (int(t_sle * f_cck) + 2) / f_cck
        windows.append((start, start + NCK / f_cck))
        assert start + NCK / f_cck < t_end
    x += pad("vcck", "CCK", f"pulse(0 {vdd} {RAMP:.3e} 1n 1n {0.5 / f_cck - 1e-9:.6e} {1 / f_cck:.6e})")
    x += quiet_pads(vdd, skip=("CCK",))
    clk = net(names, names["CBCM_CLK"])
    meas = []
    for k, (a, b) in enumerate(windows):
        meas += [(f"qd{k}", f"integ i(vvcd) from={a:.6e} to={b:.6e}"),
                 (f"qr{k}", f"integ i(vvcr) from={a:.6e} to={b:.6e}"),
                 # CCK rises 20 ns after each whole microsecond: NCK rises in the window when gated through
                 (f"ck{k}", f"when v({clk})={vdd / 2} rise={NCK} from={a:.6e} to={b:.6e}"),
                 (f"ckmax{k}", f"max v({clk}) from={a:.6e} to={b:.6e}"),
                 (f"ckmin{k}", f"min v({clk}) from={a:.6e} to={b:.6e}")]
        meas += [(f"e{k}_CBCM_EN{i}", f"find v({names[f'CBCM_EN{i}']}) at={(a + b) / 2:.6e}") for i in range(10)]
    x += control(f"tran 1n {marks[-1][1]:.6e} 0 10n uic", meas)
    return deck(corner, temp, vdd, x, reltol=CBCM_RELTOL), windows


def cbcm(args):
    corner, temp, vdd = args
    net_, windows = cbcm_net(corner, temp, vdd)
    r = run(net_, f"chip_cbcm_{corner}_{temp}")
    out = {}
    for k, (name, f) in enumerate(zip(("cell1", "cell0", "idle"), F_CBCM)):
        qd, qr = -value(r, f"qd{k}"), -value(r, f"qr{k}")      # charge drawn from VCD / VCR
        en = [f"CBCM_EN{i}" for i in range(10)]
        out[name] = {"qd": qd / NCK, "qr": qr / NCK, "c": (qd - qr) / NCK / 5.0,
                     "ck_rises": int(not math.isnan(value(r, f"ck{k}"))) * NCK,
                     "ck_swing": value(r, f"ckmax{k}") - value(r, f"ckmin{k}"),
                     "en_wrong": wrong_lines(r, f"e{k}", f, vdd, keys=en)}
    # the block's own netlist (cbcm_block.py) reading the same plate at the same corner
    import cbcm_block
    rb = run(cbcm_block.netlist(1, corner=corner, temp=temp, vdd=vdd), f"chip_cbcm_block_{corner}_{temp}")
    out["block_cell1"] = value(rb, "c")
    out["pip"] = PIP_C
    return out


# ---- RO bank through the divider -------------------------------------------------------------------
# The RO runs are long (2.3 us at 0.1 ns steps); what they check is a ratio inside one run (OUT against
# ro_in0) and the same ring in the block netlist at the same reltol.
RO_RELTOL = "1e-3"


def ro_net(corner, temp, vdd, rosel, t_run, par="", load=None, post=""):
    lines, names, devs = chip_netlist()
    x, marks, edges = scan_sources([frame(mode=3, rosel=rosel, osel=1)], vdd, holds=[t_run])
    s1, tend = marks[0]
    x += quiet_pads(vdd)
    tap = names.get(f"RO_IN{rosel}")               # RO 3 (FO4) is not built: no tap net
    still = {f"RO_IN{i}": names[f"RO_IN{i}"] for i in RO_BUILT if i != rosel}
    if rosel not in RO_BUILT:                                 # nothing may run: the mux and OUT too
        still.update(RO_MUX=net(names, "ctrl_RO_MUX"), OUT="OUT")
    t0, ta = s1 + 0.3e-6, s1 + 0.1e-6
    meas = [(f"e_RO_EN{i}", f"find v({names[f'RO_EN{i}']}) at={s1 + 0.2e-6:.6e}") for i in RO_BUILT]
    if tap:
        meas += [("tr1", f"when v({tap})={vdd / 2} rise=5 from={t0:.6e}"),
                 ("tr2", f"when v({tap})={vdd / 2} rise=25 from={t0:.6e}")]
    # OUT (the divider's last stage once osel = 1) changes every 128 RO periods: its first two crossings
    meas += [("to1", f"when v(OUT)={vdd / 2} cross=1 from={ta:.6e}"),
             ("to2", f"when v(OUT)={vdd / 2} cross=2 from={ta:.6e}")]
    for k, (label, node) in enumerate(still.items()):
        meas += [(f"smax{k}", f"max v({node}) from={ta:.6e} to={tend:.6e}"),
                 (f"smin{k}", f"min v({node}) from={ta:.6e} to={tend:.6e}")]
    x += control(f"tran 0.1n {tend:.6e} {s1:.6e} uic", meas, post)
    return deck(corner, temp, vdd, x, reltol=RO_RELTOL, par=par, load=load), list(still)


def ro(args):
    corner, temp, vdd, rosel, t_run = args
    net_, still = ro_net(corner, temp, vdd, rosel, t_run)
    r = run(net_, f"chip_ro{rosel}_{corner}_{temp}")
    state = frame(mode=3, rosel=rosel, osel=1)
    out = {"en_wrong": wrong_lines(r, "e", state, vdd, keys=[f"RO_EN{i}" for i in RO_BUILT]),
           "swing": {s: value(r, f"smax{k}") - value(r, f"smin{k}") for k, s in enumerate(still)},
           "t_half": value(r, "to2") - value(r, "to1"),                 # half an OUT period: 128 RO periods
           "f_ro": 20 / (value(r, "tr2") - value(r, "tr1"))}
    if rosel == 0:
        # the block's own netlist (ro_post.py) without any wiring load, the same ring and tap, at the
        # same reltol (it alone moves the frequency: the block reads 135.7 MHz at 1e-4, 134.2 at 1e-3)
        import ro_post
        rb = run(ro_post.ro_netlist(0, "inv", {}, corner, temp, vdd, reltol=RO_RELTOL), f"chip_ro0_block_{corner}_{temp}")
        out["f_block"] = value(rb, "f")
    return out


def main():
    chip_netlist()                                          # LVS once, before the workers fork
    jobs = {("scan", c): (scan, (c, t, v)) for c, t, v in SCAN_CORNERS}
    jobs.update({("ro", 0): (ro, ("TT", 27, 5.0, 0, 2.3e-6)), ("cbcm", "TT"): (cbcm, ("TT", 27, 5.0)),
                 ("ro", 3): (ro, ("TT", 27, 5.0, 3, 1.0e-6))})
    with ProcessPoolExecutor() as ex:
        fut = {k: ex.submit(f, a) for k, (f, a) in jobs.items()}
        res = {k: f.result() for k, f in fut.items()}
    for (kind, key), r in res.items():
        print(kind, key, r)
    return res


if __name__ == "__main__":
    main()
