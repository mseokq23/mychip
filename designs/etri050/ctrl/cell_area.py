#!/usr/bin/env python3
"""Count standard cells in a gate-level Verilog netlist and sum their LEF footprints.

usage: cell_area.py <netlist.v> <stdcells.lef> [top_module]

The area is the sum of cell boxes (SIZE in the LEF), i.e. 100 % placement density;
routing and filler are not included.
"""
import re
import sys
from collections import Counter


def lef_sizes(path):
    text = open(path).read()
    sizes = {}
    for m in re.finditer(r'MACRO\s+(\S+)(.*?)END\s+\1', text, re.S):
        s = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', m.group(2))
        if s:
            sizes[m.group(1)] = (float(s.group(1)), float(s.group(2)))
    return sizes


def cell_counts(path, sizes, top=None):
    text = open(path).read()
    if top:
        m = re.search(r'\bmodule\s+%s\b(.*?)\bendmodule\b' % re.escape(top), text, re.S)
        if not m:
            sys.exit(f'module {top} not found in {path}')
        text = m.group(1)
    counts = Counter()
    for m in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(\\\S+|[A-Za-z_][\w$]*)\s*\(', text, re.M):
        if m.group(1) in sizes:
            counts[m.group(1)] += 1
    return counts


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sizes = lef_sizes(sys.argv[2])
    counts = cell_counts(sys.argv[1], sizes, sys.argv[3] if len(sys.argv) > 3 else None)
    total_n, total_a = 0, 0.0
    print(f"{'cell':10s} {'count':>5s} {'w x h (um)':>12s} {'area (um2)':>11s}")
    for name in sorted(counts):
        w, h = sizes[name]
        a = counts[name] * w * h
        total_n += counts[name]
        total_a += a
        print(f"{name:10s} {counts[name]:5d} {w:5.1f} x {h:4.1f} {a:11.0f}")
    print(f"{'total':10s} {total_n:5d} {'':12s} {total_a:11.0f}  ({total_a / 1e6:.4f} mm2)")


if __name__ == '__main__':
    main()
