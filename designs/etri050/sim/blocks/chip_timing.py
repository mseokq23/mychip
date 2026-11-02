"""Control block timing with the drawn wiring: scan chain races, clock to Q, read-back, RO divider.

chip_post.py runs the chip core from the LVS netlist with its devices alone, so the control block's
wiring was simulated nowhere (its qflow STA is no sign-off). Here every net of the core also carries
its wiring capacitance from the drawn GDS (designs/etri050/chip/chip_rc.py: rule document v1.1 table
5.5, the method of cbcm_c.py and ro_post.py, whose block nodes it reproduces to 0.01 fF), and OUT drives
the drawn input stage of the POB4 pad cell (chip_rc.pob4_input) instead of chip_post's 0.1 pF.

  scan     chip_post's five frames at 10 MHz, TT 27 C 5 V, SS 125 C 4.5 V, FF 27 C 5.5 V, and for hold
           FF 0 C 5.5 V (a cold lab), FS and SF 27 C 5 V: the select and enable lines and the
           read-back as chip_post checks them. From the waveforms, at every SCK rising edge (VDD / 2
           crossings, linear between the simulator's points):
             shifts     each shift flop changes at an edge exactly when the bit stream says (once frame 1
                        has filled the register) and never between edges
             race       t(sr[i] changes) - t(the clock of the flop that takes sr[i] rises), 19 pairs, 7
                        of them across two of the four clock buffers (sck_bF$buf0-3): the hold time of
                        DFFPOSX1 must stay below it
             clk->Q     per flop; insertion delay SCK port -> buffer outputs (also per buffer), skew
             read-back  SCK port -> OUT port (osel = 0: OUT follows sr[19])
             SDI        the pad's change against the clock of sr[0]'s flop (set by the controller's
                        firmware: 25 ns before the rising edge and 75 ns after it in these runs)
  lateral  the scan at SS and FF with same-layer coupling (no table value; chip_rc.lateral, an upper
           estimate) doubled on SCK and the four buffer outputs alone: the clocks as late as the wiring
           could make them. All buffers move together here, so the skew that coupling on one buffer
           alone could add is taken from it: each buffer's insertion delay increase over the scan run
  dff      DFFPOSX1 alone, the drawn devices of the sr[1] flop with their wiring and its in-circuit load:
           hold and setup time (D at VDD / 2 against CLK at VDD / 2) at each corner, the clock ramp as
           slow as the slowest seen in that corner's scan, the data ramp the fastest and the slowest
           seen (hold: the worse; setup: the slowest)
  ro       RO 0 (INV, the fastest ring) through the 8-stage ripple divider (mode 11, osel = 1) at the
           three corners: each divider stage that toggles at least twice in the 1.2 us window runs at
           exactly 1/2, 1/4, ... of the tap's frequency, and the RO mux passes the ring rail to rail

hold slack = min race - hold time. The wire resistance is not simulated: chip_rc.r_bound times the clock
net's whole capacitance (wiring with the lateral estimate + the gates on it) bounds the Elmore delay to
any flop. A pair across two buffers can see SCK's bound (the buffer inputs) and its capture buffer's,
so the slack must exceed SCK's bound + the largest buffer's, and the one-buffer lateral skew above
(run_all.py). Setup: the shortest SCK period is max race + setup time.

usage: python3 chip_timing.py [--reuse]   (needs designs/etri050/chip/build: run_chip.sh; about 75 min
       on 2 cores; --reuse reads a run's log and waveforms again when its deck is unchanged)
"""
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

import chip_post as cp
from simlib import BUILD, header, results, run

HERE = Path(__file__).resolve().parent
CHIP = HERE.parents[1] / "chip"
CTRL_V = HERE.parents[1] / "ctrl/macro/teg_ctrl.v"
sys.path.insert(0, str(CHIP))

NAN = float("nan")
CORNERS = cp.SCAN_CORNERS
HOLD_CORNERS = (("FF", 0, 5.5), ("FS", 27, 5.0), ("SF", 27, 5.0))   # the scan and DFFPOSX1 alone, for hold
BRACKET = ("SS", "FF")
CLOCKS = ["SCK"] + [f"ctrl.SCK_BF$BUF{b}" for b in range(4)]
SR = [f"ctrl.SR[{i}]" for i in range(cp.NBIT)]
TNODES = ["SCK", "SDI", "SLE", "OUT"] + CLOCKS[1:] + SR
WIN = (-1e-9, 45e-9)            # an edge's window around the SCK source's rising ramp (SCK falls at +49 ns)
T_RO = 1.5e-6                   # RO runs: time after SLE; the window starts 0.3 us after it
RO_NODES = ["RO_IN0", "ctrl.RO_MUX"] + [f"ctrl._G_DIV[{k}].Q_" for k in range(8)]
GATE = {"NFET": (2.9739, 0.3134), "PFET": (2.9624, 0.2138)}   # rule document 5.5 poly gate: fF/um2, fF/um


# ---- the circuit ------------------------------------------------------------------------------------
def chain():
    """The 20 shift flops in order, from the frozen macro: [(Q, instance, D, CLK)], chip net names."""
    lines, names, devs = cp.chip_netlist()

    def chip_net(n):
        for c in ("ctrl." + n.upper(), n.upper()):              # inner net, or a macro port's chip net
            if c in names:
                return c
        raise SystemExit(f"no chip net for the macro net {n}")

    by_q = {}
    for cell, inst, body in re.findall(r"^(\w+)\s+(\S+)\s*\((.*?)\);", CTRL_V.read_text(), re.S | re.M):
        if cell == "DFFPOSX1":
            pins = {k: v.strip() for k, v in re.findall(r"\.(\w+)\(([^()]*)\)", body)}
            by_q[chip_net(pins["Q"])] = (inst.upper(), chip_net(pins["D"]), chip_net(pins["CLK"]))
    out = []
    for i, q in enumerate(SR):
        inst, d, clk = by_q[q]
        if d != (SR[i - 1] if i else "SDI") or clk not in CLOCKS[1:]:
            raise SystemExit(f"{q}: D {d}, CLK {clk} is not the shift chain")
        out.append((q, inst, d, clk))
    return out


_RC = {}


def rc():
    """Wiring capacitance of every net (F), the clock nets' lateral estimate (F) and resistance bound
    (ohm), the POB4 input stage: from the GDS once per process (before the workers fork)."""
    if not _RC:
        import chip_lvs
        import chip_rc
        ok, rep, nl, keep = chip_lvs.lvs(CHIP / "build/pdkv_Top.gds", named=True, keep=True)
        if not ok:
            raise SystemExit("chip LVS does not match:\n" + "\n".join(rep))
        _RC["caps"] = chip_rc.wiring(keep)
        _RC["lat"] = chip_rc.lateral(keep, set(CLOCKS))
        _RC["rbound"] = chip_rc.r_bound(keep, set(CLOCKS))
        _RC["pob4"] = chip_rc.pob4_input(CHIP / "build/pdkv_Top.gds")
    return _RC


def gate_cap(node):
    """F of the MOS gates on a deck node (rule document 5.5 gate area and fringe values)."""
    lines, names, devs = cp.chip_netlist()
    c = 0.0
    for cls, t, p, line in devs:
        if cls in GATE and t["G"] == node:
            area, fringe = GATE[cls]
            c += area * p["W"] * p["L"] + fringe * 2 * p["W"]
    return c * 1e-15


def par(extra=None):
    """The deck's wiring capacitance lines; extra = {net: F} added to some nets (the lateral bracket)."""
    lines, names, devs = cp.chip_netlist()
    caps = dict(rc()["caps"])
    for k, c in (extra or {}).items():
        caps[k] = caps.get(k, 0.0) + c
    out = [f"* wiring capacitance of {len(caps)} nets (chip_rc.py)"]
    for k, (nm, c) in enumerate(sorted(caps.items())):
        node = names.get(nm)
        if node is None:
            raise SystemExit(f"wiring: no net {nm} in the chip netlist")
        if node not in ("0", "VDD") and c > 0:
            out.append(f"cw{k} {node} 0 {c:.4g}")
    return "\n".join(out) + "\n"


def load():
    """What OUT drives: the drawn POB4 input stage, its output loaded by the next stage's gates."""
    p = rc()["pob4"]
    node = {"X": "pob4_x", "VDD": "VDD", "VSS": "0"}
    x = "* OUT: the drawn input stage of POB4 (chip_rc.pob4_input)\n"
    for k, (cls, t, q) in enumerate(p["devices"]):
        model, bulk = ("nmos4", "0") if cls == "NFET" else ("pmos4", "VDD")
        x += (f"Mpob{k} {node[t['D']]} OUT {node[t['S']]} {bulk} {model} w={q['W']:.4g}u l={q['L']:.4g}u "
              f"ad={q['AD']:.4g}p as={q['AS']:.4g}p pd={q['PD']:.4g}u ps={q['PS']:.4g}u\n")
    return x + f"cpob4_a OUT 0 {p['wire_a']:.4g}\ncpob4_x pob4_x 0 {p['c_x_gates'] + p['wire_x']:.4g}\n"


def elmore():
    """{clock net: s}: resistance bound x (wiring + lateral estimate + gates) of each clock net."""
    lines, names, devs = cp.chip_netlist()
    r = rc()
    return {n: r["rbound"][n] * (r["caps"][n] + r["lat"][n] + gate_cap(names[n])) for n in CLOCKS}


# ---- waveforms ----------------------------------------------------------------------------------------
def wrdata(name, nodes):
    lines, names, devs = cp.chip_netlist()
    return ("set wr_singlescale\nset wr_vecnames\noption numdgt=8\n"
            f"wrdata {name}.dat " + " ".join(f"v({names[n]})" for n in nodes) + "\n")


def waves(name, nodes):
    path = os.path.join(BUILD, f"{name}.dat")
    with open(path) as f:
        head = f.readline().split()
    if len(head) != len(nodes) + 1:
        raise SystemExit(f"{path}: {len(head)} columns for {len(nodes)} nodes")
    d = np.loadtxt(path, skiprows=1)
    return d[:, 0], {n: d[:, k + 1] for k, n in enumerate(nodes)}


def crossings(t, v, level):
    """Times (linear between points) and directions (+1 rising) where v crosses level."""
    s = v - level
    i = np.nonzero(np.signbit(s[:-1]) != np.signbit(s[1:]))[0]
    return t[i] - s[i] * (t[i + 1] - t[i]) / (s[i + 1] - s[i]), np.where(s[i + 1] > s[i], 1, -1)


class Edges:
    """Crossings of VDD / 2 and the 10-90 % times of the transitions through them."""

    def __init__(self, t, v, vdd):
        self.mid = {n: crossings(t, w, vdd / 2) for n, w in v.items()}
        self.lo = {n: crossings(t, w, 0.1 * vdd) for n, w in v.items()}
        self.hi = {n: crossings(t, w, 0.9 * vdd) for n, w in v.items()}

    def at(self, n, a, b, direction=0):
        tc, dr = self.mid[n]
        m = (tc >= a) & (tc < b) & ((dr == direction) if direction else True)
        return tc[m], dr[m]

    def slew(self, n, tc, dr):
        (lt, ld), (ht, hd) = self.lo[n], self.hi[n]
        if dr > 0:
            a, b = lt[(lt <= tc) & (ld > 0)], ht[(ht >= tc) & (hd > 0)]
        else:
            a, b = ht[(ht <= tc) & (hd < 0)], lt[(lt >= tc) & (ld < 0)]
        return b[0] - a[-1] if len(a) and len(b) else NAN


def stream():
    """The bits in the order they are shifted in (MSB of each frame first)."""
    return [(f >> i) & 1 for f in cp.F_SCAN for i in range(cp.NBIT - 1, -1, -1)]


def scan_timing(e, edges, ch):
    """Races, clock to Q, skew, read-back and the shift pattern from the crossings of one scan run."""
    s = stream()
    buf = {q: clk for q, inst, d, clk in ch}
    recv = {d: q for q, inst, d, clk in ch}                   # sr[i] -> the flop that takes it
    races = {q: [] for q in SR[:-1]}
    c2q, skew, ins, rb, slew_c, slew_q, clk0 = [], [], [], [], [], [], []
    ins_buf = {c: [] for c in CLOCKS[1:]}
    wrong = checked = multi = 0
    for k, te in enumerate(edges):
        a, b = te + WIN[0], te + WIN[1]
        sck = e.at("SCK", a, b, +1)[0]
        tclk = {}
        for c in CLOCKS[1:]:
            tc, dr = e.at(c, a, b, +1)
            if len(tc) != 1 or len(sck) != 1:
                raise SystemExit(f"edge {k}: {c} rises {len(tc)} times, SCK {len(sck)}")
            tclk[c] = tc[0]
            slew_c.append(e.slew(c, tc[0], +1))
            ins.append(tc[0] - sck[0])
            ins_buf[c].append(tc[0] - sck[0])
        skew.append(max(tclk.values()) - min(tclk.values()))
        clk0.append(tclk[buf[SR[0]]])
        for i, q in enumerate(SR):
            tc, dr = e.at(q, a, b)
            multi += len(tc) > 1
            if k - i - 1 >= 0:                                 # its value before the edge is known
                checked += 1
                wrong += (len(tc) == 1) != (s[k - i] != s[k - i - 1])
            if len(tc):
                c2q.append(tc[0] - tclk[buf[q]])
                slew_q.append(e.slew(q, tc[0], dr[0]))
                if q in recv:
                    races[q].append(tc[0] - tclk[buf[recv[q]]])
        out = e.at("OUT", a, b)[0]
        if len(out):
            rb.append(out[0] - sck[0])
    # changes of the shift flops away from every edge window (after the first edge)
    stray = 0
    for q in SR:
        tc = e.mid[q][0]
        tc = tc[tc > edges[0] + WIN[0]]
        inside = np.zeros(len(tc), bool)
        for te in edges:
            inside |= (tc >= te + WIN[0]) & (tc < te + WIN[1])
        stray += int((~inside).sum())
    # SDI against the clock of sr[0]'s flop: each change after the edge before it and before the next
    sdi = e.mid["SDI"][0]
    clk0 = np.array(clk0)
    after = [x - clk0[clk0 < x][-1] for x in sdi if (clk0 < x).any()]
    before = [clk0[clk0 > x][0] - x for x in sdi if (clk0 > x).any()]
    pair = {q: min(v) for q, v in races.items() if v}
    worst = min(pair, key=pair.get)
    return {"race_min": pair[worst], "race_pair": f"{worst} -> {recv[worst]}",
            "race_max": max(max(v) for v in races.values() if v),
            "race_pairs": len(pair), "race_by_pair": pair,
            "cross_buffer": {q: pair[q] for q in pair if buf[q] != buf[recv[q]]},
            "c2q": (min(c2q), max(c2q)), "skew_max": max(skew), "ins": (min(ins), max(ins)),
            "ins_by_buf": {c: float(np.mean(v)) for c, v in ins_buf.items()},
            "readback_max": max(rb) if rb else NAN, "readback_edges": len(rb),
            "slew_clk_max": max(x for x in slew_c if not math.isnan(x)),
            "slew_q_max": max(x for x in slew_q if not math.isnan(x)),
            "slew_q_min": min(x for x in slew_q if not math.isnan(x)),
            "shift_wrong": wrong, "shift_checked": checked, "multi": multi, "stray": stray,
            "sdi_after_min": min(after) if after else NAN, "sdi_before_min": min(before) if before else NAN}


# ---- runs ---------------------------------------------------------------------------------------------
REUSE = False


def run_once(net, name, files=()):
    """run(), or with --reuse the results of the last run of this very deck (its log and files)."""
    path = os.path.join(BUILD, name)
    keep = [path + ".cir", path + ".log"] + [os.path.join(BUILD, f) for f in files]
    if REUSE and all(os.path.exists(f) for f in keep) and open(path + ".cir").read() == net:
        return results(open(path + ".log").read())
    return run(net, name)


def scan_t(args):
    corner, temp, vdd, tag, extra = args
    name = f"chip_timing_{tag}_{corner}_{temp}"
    deck_ = cp.scan_net(corner, temp, vdd, par=par(extra), load=load(), post=wrdata(name, TNODES))
    r = run_once(deck_, name, [name + ".dat"])
    out = cp.scan_result(r, vdd)
    x, marks, edges = cp.scan_sources(cp.F_SCAN, vdd)
    t, v = waves(name, TNODES)
    out.update(scan_timing(Edges(t, v, vdd), edges, chain()))
    return out


def ro_t(args):
    corner, temp, vdd = args
    name = f"chip_timing_ro0_{corner}_{temp}"
    deck_, still = cp.ro_net(corner, temp, vdd, 0, T_RO, par=par(), load=load(), post=wrdata(name, RO_NODES))
    r = run_once(deck_, name, [name + ".dat"])
    x, marks, edges = cp.scan_sources([cp.frame(mode=3, rosel=0, osel=1)], vdd, holds=[T_RO])
    s1, tend = marks[0]
    a = s1 + 0.3e-6
    t, v = waves(name, RO_NODES)
    m = t >= a
    e = Edges(t[m], {n: w[m] for n, w in v.items()}, vdd)
    period = {}
    for n in RO_NODES:
        up = e.mid[n][0][e.mid[n][1] > 0]
        period[n] = (up[-1] - up[0]) / (len(up) - 1) if len(up) >= 3 else NAN
    tap = period["RO_IN0"]
    stages = {k: period[f"ctrl._G_DIV[{k}].Q_"] / tap / 2 ** (k + 1) for k in range(8)}
    mux, tm = v["ctrl.RO_MUX"][m], t[m]
    high = float(np.sum(np.diff(tm) * (mux[:-1] > vdd / 2)) / (tm[-1] - tm[0]))
    state = cp.frame(mode=3, rosel=0, osel=1)
    return {"f_tap": 1 / tap, "f_mux_vs_tap": tap / period["ctrl.RO_MUX"],
            "stages": {k: s for k, s in stages.items() if not math.isnan(s)},
            "mux_min": float(mux.min()), "mux_max": float(mux.max()), "mux_high": high,
            "en_wrong": cp.wrong_lines(r, "e", state, vdd, keys=[f"RO_EN{i}" for i in cp.RO_BUILT])}


# ---- DFFPOSX1 alone -------------------------------------------------------------------------------
def dff_netlist():
    """The drawn devices of the flop that drives sr[1] (pins renamed d / clk / q), the wiring of its
    inner nets, and q's load in the chip (its wiring and the gates of the flops that take sr[1])."""
    lines, names, devs = cp.chip_netlist()
    q, inst, d, clk = chain()[1]
    pre = f"ctrl.{inst}."
    inner = {names[k]: k for k in names if k.startswith(pre)}
    pin = {names[d]: "d", names[clk]: "clk", names[q]: "q"}
    out = []
    for cls, t, p, line in devs:
        if not set(t.values()) & set(inner):
            continue
        bad = [v for v in t.values() if v not in inner and v not in pin and v not in ("VDD", "0")]
        if cls not in GATE or bad:
            raise SystemExit(f"{inst}: device {line} reaches {bad or cls}")
        t = {k: pin.get(v, v) for k, v in t.items()}
        model = "nmos4" if cls == "NFET" else "pmos4"
        out.append(f"M{len(out)} {t['D']} {t['G']} {t['S']} {t['B']} {model} w={p['W']:.4g}u l={p['L']:.4g}u "
                   f"ad={p['AD']:.4g}p as={p['AS']:.4g}p pd={p['PD']:.4g}u ps={p['PS']:.4g}u")
    caps = rc()["caps"]
    out += [f"cw{k} {n} 0 {caps[name]:.4g}" for k, (n, name) in enumerate(sorted(inner.items())) if name in caps]
    own = sum(GATE[c][0] * p["W"] * p["L"] + GATE[c][1] * 2 * p["W"] for c, t, p, l in devs
              if c in GATE and t["G"] == names[q] and not set(t.values()) & set(inner)) * 1e-15
    out.append(f"cq q 0 {caps[q] + own:.4g}")
    return "\n".join(out) + "\n", len([x for x in out if x.startswith("M")])


def pwl(points):
    return "pwl(" + " ".join(f"{t:.6e} {v:.6g}" for t, v in points) + ")"


def dff_run(corner, temp, vdd, sl_clk, sl_d, mode, delta, v0):
    """One transient: CLK rises at 5 ns (taking D = v0), falls at 15, rises at 25 (the edge under test)
    and falls at 35 ns. hold: D changes to the other value at 25 ns + delta and Q must stay within 10 %
    of VDD of v0 until 34 ns. setup: D changes at 25 ns - delta; returns the delay from the edge to Q
    crossing VDD / 2 (NaN when it does not)."""
    body, n = dff_netlist()
    rc_, rd = sl_clk / 0.8, sl_d / 0.8                        # ramps whose 10-90 % times are the slews
    ta, f1, tc, f2 = 5e-9, 15e-9, 25e-9, 35e-9
    clk = pwl([(0, 0)] + [(x, y) for t0, up in ((ta, 1), (f1, 0), (tc, 1), (f2, 0))
                          for x, y in ((t0 - rc_ / 2, vdd * (1 - up)), (t0 + rc_ / 2, vdd * up))])
    tch = tc + delta if mode == "hold" else tc - delta
    a, b = v0 * vdd, (1 - v0) * vdd
    # the sources reach their pins through 10 ohm: a source that only charges gates has a branch current
    # of nothing but rounding, and ngspice stops at the first breakpoint (as chip_post.R_PAD). VDD goes
    # through 1 ohm: with a 0.37 ns data ramp (TT's fastest Q) ngspice stopped at the ramp's start on
    # vdd#branch ("timestep too small"); 1 ohm drops at most a mV
    x = header(corner, temp, method="gear", abstol="1e-12") + f"vdd vdd_s 0 {vdd}\nrvdd vdd_s VDD 1\n"
    x += f"vclk clk_s 0 {clk}\nrclk clk_s clk 10\nvd d_s 0 {pwl([(0, a), (tch - rd / 2, a), (tch + rd / 2, b)])}\nrd d_s d 10\n"
    x += body + ".control\nset noaskquit\ntran 2p 40n 0 2p\n"
    x += f"meas tran qi find v(q) at={tc - 1e-9:.6e}\n"
    if mode == "hold":
        x += f"meas tran qmax max v(q) from={tc:.6e} to={f2 - 1e-9:.6e}\nmeas tran qmin min v(q) from={tc:.6e} to={f2 - 1e-9:.6e}\n"
        x += 'echo "RES qi=$&qi qmax=$&qmax qmin=$&qmin"\n'
    else:
        x += f"meas tran tq when v(q)={vdd / 2} cross=1 from={tc - 2e-9:.6e} to={f2 - 1e-9:.6e}\n"
        x += f"meas tran qe find v(q) at={f2 - 1e-9:.6e}\n" + 'echo "RES qi=$&qi tq=$&tq qe=$&qe"\n'
    x += "quit\n.endc\n.end\n"
    name = f"chip_timing_dff_{corner}_{temp}_{mode}{v0}"
    r = run(x, name)
    if math.isnan(cp.value(r, "qi")):
        raise SystemExit(f"DFFPOSX1 {corner} {temp} C: {name} did not finish (build/{name}.log)")
    if abs(cp.value(r, "qi") - a) > 0.1 * vdd:
        raise SystemExit(f"DFFPOSX1 {corner}: Q did not take D = {v0} at the first edge")
    if mode == "hold":
        dev = max(abs(cp.value(r, "qmax") - a), abs(cp.value(r, "qmin") - a))
        return dev < 0.1 * vdd
    tq = cp.value(r, "tq")
    return tq - tc if abs(cp.value(r, "qe") - b) < 0.1 * vdd else NAN


def bisect(ok, lo, hi, tol=1e-12):
    """The smallest x with ok(x) between lo (not ok) and hi (ok)."""
    if ok(lo) or not ok(hi):
        raise SystemExit(f"bisect: no boundary in [{lo}, {hi}]")
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def dff(corner, temp, vdd, sl_clk, sl_d):
    """Hold and setup time (s) of the drawn DFFPOSX1, the worse of D rising and D falling; sl_d = (the
    fastest, the slowest data ramp seen). Hold: the worse of the two ramps. Setup (the slowest ramp):
    the smallest lead for which the edge-to-Q delay stays within 10 % of its value with an 8 ns lead."""
    hold, setup, c2q = {}, [], []
    fast, slow = sl_d
    for v0 in (0, 1):
        for sl in (fast, slow):
            hold[(v0, sl)] = bisect(lambda dl: dff_run(corner, temp, vdd, sl_clk, sl, "hold", dl, v0), -2e-9, 3e-9)
        ref = dff_run(corner, temp, vdd, sl_clk, slow, "setup", 8e-9, v0)
        c2q.append(ref)

        def ok(dl):
            tq = dff_run(corner, temp, vdd, sl_clk, slow, "setup", dl, v0)
            return not math.isnan(tq) and tq <= 1.1 * ref

        setup.append(bisect(ok, -1e-9, 8e-9))
    return {"hold": max(hold.values()), "hold_fast_ramp": max(hold[(v, fast)] for v in (0, 1)),
            "hold_slow_ramp": max(hold[(v, slow)] for v in (0, 1)), "setup": max(setup), "c2q": c2q,
            "slews": {"clk": sl_clk, "d_fast": fast, "d_slow": slow}, "devices": dff_netlist()[1]}


# ---- all -----------------------------------------------------------------------------------------------
def main(reuse=None):
    global REUSE
    REUSE = "--reuse" in sys.argv[1:] if reuse is None else reuse
    cp.chip_netlist()                                       # LVS and wiring once, before the workers fork
    r = rc()
    bracket = {n: 2 * r["lat"][n] for n in CLOCKS}
    jobs = {("ro", c, t): (ro_t, (c, t, v)) for c, t, v in CORNERS}
    jobs.update({("scan", c, t): (scan_t, (c, t, v, "scan", None)) for c, t, v in CORNERS + HOLD_CORNERS})
    jobs.update({("lateral", c, t): (scan_t, (c, t, v, "lateral", bracket)) for c, t, v in CORNERS if c in BRACKET})
    with ProcessPoolExecutor() as ex:
        fut = {k: ex.submit(f, a) for k, (f, a) in jobs.items()}
        res = {k: f.result() for k, f in fut.items()}
    for c, t, v in CORNERS + HOLD_CORNERS:
        s = [res[(k, c, t)] for k in ("scan", "lateral") if (k, c, t) in res]
        res[("dff", c, t)] = dff(c, t, v, max(x["slew_clk_max"] for x in s),
                                 (min(x["slew_q_min"] for x in s), max(x["slew_q_max"] for x in s)))
    res["elmore"] = elmore()
    res["lat"] = {n: r["lat"][n] for n in CLOCKS}
    res["rbound"] = {n: r["rbound"][n] for n in CLOCKS}
    res["pob4"] = {k: v for k, v in r["pob4"].items() if k != "devices"}
    for k, v in res.items():
        print(k, v)

    def plain(x):
        if isinstance(x, dict):
            return {str(k): plain(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [plain(v) for v in x]
        return float(x) if isinstance(x, (float, np.floating)) else x

    with open(os.path.join(BUILD, "chip_timing.json"), "w") as f:
        json.dump({" ".join(map(str, k)) if isinstance(k, tuple) else k: plain(v) for k, v in res.items()}, f, indent=1)
    return res


if __name__ == "__main__":
    main()
