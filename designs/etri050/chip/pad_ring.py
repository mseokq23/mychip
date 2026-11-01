#!/usr/bin/env python3
"""Write the pdkv pad ring (pdkv_Pad.mag) from the kit's 28-pin GPIO template.

The kit template pads_ETRI/MPW_PAD_28Pin_IO.mag places 28 PIC cells (PAD_0 .. PAD_27), four
corner cells and fillers on the 1.9 x 1.9 mm frame with a 135 um pad pitch. Each PIC is replaced
by the cell the pin needs (pins.csv) at the template's own placement; the kit's FIR_PE and pong_pt1
chips were made from the same template this way. The script checks the template order from the
transforms before it writes anything:
  S1..S7 = PAD_0..PAD_6 (left to right)      E1..E7 = PAD_7..PAD_13 (bottom to top)
  N1..N7 = PAD_20..PAD_14 (left to right)    W1..W7 = PAD_27..PAD_21 (bottom to top)

It also writes pad_pins.json: for every pad the core-side port (PANA PAD or PADR, PIC Y, POB4 A,
PVDD VDD, PVSS VSS) as a metal2 rectangle in die coordinates (um), for the pin routing.

usage: pad_ring.py [--kit DIR] [--force-port PAD|PADR] [--outdir DIR]
  --force-port PADR connects the force and heater pins (port PAD in pins.csv) through the PANA series
  resistor instead (kept as an option until ETRI answers whether the direct port may be used).
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAMBDA = 0.3  # um


def unit_um(lines):
    """Size of one .mag coordinate unit in um (from the 'magscale a b' line, default lambda)."""
    for line in lines[:6]:
        if line.startswith('magscale'):
            a, b = (int(v) for v in line.split()[1:3])
            return LAMBDA * a / b
    return LAMBDA


def template_uses(lines):
    """[(line_index, cell, instance, (a, b, c, d, e, f))] for every 'use' in a .mag file."""
    out = []
    for i, line in enumerate(lines):
        if line.startswith('use '):
            parts = line.split()
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].startswith('transform'):
                    out.append((i, parts[1], parts[2], tuple(int(v) for v in lines[j].split()[1:7])))
                    break
    return out


def cell_ports(path):
    """Port name -> (x1, y1, x2, y2) in um (cell coordinates): the metal2/m2p rectangle under each m2p label,
    plus the bond pad label point under 'space'."""
    lines = open(path).read().splitlines()
    u = unit_um(lines)
    rects, section = [], None
    ports = {}
    for line in lines:
        if line.startswith('<< '):
            section = line[3:-3].strip()
            continue
        if section in ('m2p', 'metal2') and line.startswith('rect'):
            rects.append(tuple(int(v) for v in line.split()[1:5]))
        if line.startswith('flabel'):
            p = line.split()
            at = 3 if p[2] == 's' else 2            # 'flabel <layer> [s] x1 y1 x2 y2 ...' (s = sticky)
            layer, x, y, name = p[1], int(p[at]), int(p[at + 1]), p[-1]
            if layer == 'm2p':
                hit = [r for r in rects if r[0] <= x <= r[2] and r[1] <= y <= r[3]]
                if not hit:
                    sys.exit(f"{path}: no metal2 rectangle under label {name}")
                ports[name] = tuple(v * u for v in hit[0])
            elif layer == 'space':
                ports['_bond'] = (x * u, y * u, x * u, y * u)
    return ports


def place(t, k, u_parent, pt):
    """Child point (um) -> parent point (um) through a .mag transform (parent units)."""
    a, b, c, d, e, f = t
    x, y = pt[0] / u_parent, pt[1] / u_parent
    return ((a * x + b * y + c) * u_parent, (d * x + e * y + f) * u_parent)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kit', default=os.environ.get('ETRI050_DK', os.path.expanduser('~/ETRI050_DesignKit')))
    ap.add_argument('--force-port', choices=('PAD', 'PADR'), default='PAD')
    ap.add_argument('--outdir', default=os.path.join(HERE, 'build'))
    ap.add_argument('--name', default='pdkv')
    args = ap.parse_args()

    tpl_path = os.path.join(args.kit, 'pads_ETRI', 'MPW_PAD_28Pin_IO.mag')
    lib = os.path.join(args.kit, 'pads_ETRI', 'GDS_Magic')
    tpl = open(tpl_path).read().splitlines()
    u_parent = unit_um(tpl)
    uses = {inst: (i, cell, t) for i, cell, inst, t in template_uses(tpl)}

    # where each template pad really is (bond pad centre in die coordinates)
    pic = cell_ports(os.path.join(lib, 'PIC.mag'))
    centre = {}
    for k in range(28):
        i, cell, t = uses[f'PAD_{k}']
        assert cell == 'PIC', (k, cell)
        centre[k] = place(t, 1, u_parent, pic['_bond'][:2])
    side_of = {}
    for k, (x, y) in centre.items():
        side_of[k] = min((('S', y), ('N', 1900 - y), ('W', x), ('E', 1900 - x)), key=lambda s: s[1])[0]
    expect = {f'S{i}': i - 1 for i in range(1, 8)}
    expect.update({f'E{i}': 6 + i for i in range(1, 8)})
    expect.update({f'N{i}': 21 - i for i in range(1, 8)})
    expect.update({f'W{i}': 28 - i for i in range(1, 8)})
    for side, along in (('S', 0), ('N', 0), ('W', 1), ('E', 1)):
        ks = sorted((k for k in range(28) if side_of[k] == side), key=lambda k: centre[k][along])
        want = [expect[f'{side}{i}'] for i in range(1, 8)]
        if ks != want:
            sys.exit(f"template order on side {side} is {ks}, expected {want}")
    pitch = sorted(round(centre[k][0], 2) for k in range(7))
    print(f"template {tpl_path}: 28 PIC pads, sides and order checked, S-side centres {pitch} um")

    pins = list(csv.DictReader(open(os.path.join(HERE, 'pins.csv'), encoding='utf-8')))
    if sorted(p['pad'] for p in pins) != sorted(expect):
        sys.exit("pins.csv must list W1..W7, N1..N7, E1..E7, S1..S7 once each")
    out_lines = list(tpl)
    ports_cache, table = {}, []
    for p in pins:
        k = expect[p['pad']]
        i, _, t = uses[f'PAD_{k}']
        port = p['port']
        if p['cell'] == 'PANA' and port == 'PAD' and args.force_port == 'PADR':
            port = 'PADR'
        out_lines[i] = f"use {p['cell']}  {p['pad']}_{p['pin']}"
        if p['cell'] not in ports_cache:
            ports_cache[p['cell']] = cell_ports(os.path.join(lib, p['cell'] + '.mag'))
        cp = ports_cache[p['cell']]
        if port not in cp:
            sys.exit(f"{p['cell']} has no port {port}")
        x1, y1, x2, y2 = cp[port]
        (ax, ay), (bx, by) = place(t, 1, u_parent, (x1, y1)), place(t, 1, u_parent, (x2, y2))
        table.append({'pad': p['pad'], 'pin': p['pin'], 'cell': p['cell'], 'port': port, 'side': p['pad'][0],
                      'rect': [round(min(ax, bx), 3), round(min(ay, by), 3), round(max(ax, bx), 3), round(max(ay, by), 3)]})

    os.makedirs(args.outdir, exist_ok=True)
    mag = os.path.join(args.outdir, f'{args.name}_Pad.mag')
    open(mag, 'w').write('\n'.join(out_lines) + '\n')
    json.dump({'force_port': args.force_port, 'unit': 'um', 'pads': table},
              open(os.path.join(args.outdir, 'pad_pins.json'), 'w'), indent=1, ensure_ascii=False)
    count = {}
    for p in table:
        count[p['cell']] = count.get(p['cell'], 0) + 1
    print(f"wrote {mag}: " + ', '.join(f'{c} {n}' for c, n in sorted(count.items())) + f" (force/heater port {args.force_port})")
    for p in table:
        print(f"  {p['pad']:3s} {p['pin']:5s} {p['cell']:5s} {p['port']:4s} metal2 {p['rect']}")


if __name__ == '__main__':
    main()
