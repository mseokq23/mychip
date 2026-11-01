#!/usr/bin/env python3
"""Drop the net declarations that qflow's vlog2Verilog repeats for ANSI ports.

qflow writes the module header with ANSI ports ("input sdi,") and then declares some of the
same names again ("wire sdi ;"). Icarus Verilog 14 rejects the second declaration
("'sdi' has already been declared in this scope"). Removing exactly those lines leaves the
netlist otherwise unchanged: ANSI ports are already nets.

usage: strip_port_wires.py <in.v> <out.v>
"""
import re
import sys


def main(src_path, dst_path):
    src = open(src_path).read()
    head = re.search(r'module\s+\w+\s*\((.*?)\);', src, re.S)
    if not head:
        sys.exit(f"{src_path}: no module header found")
    ports = set(re.findall(r'(?:input|output|inout)\s*(?:\[[^\]]*\])?\s*([A-Za-z_][\w$]*)', head.group(1)))
    wire = re.compile(r'\s*wire\s*(?:\[[^\]]*\])?\s*([A-Za-z_][\w$]*)\s*;\s*$')
    kept, dropped = [], []
    for line in src.splitlines(keepends=True):
        m = wire.match(line)
        if m and m.group(1) in ports:
            dropped.append(m.group(1))
            continue
        kept.append(line)
    open(dst_path, 'w').write(''.join(kept))
    print(f"{src_path}: {len(ports)} ports, dropped {len(dropped)} repeated wire declarations: {' '.join(sorted(dropped))}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
