#!/usr/bin/env python3
"""Summarize a KLayout DRC report (.lyrdb): markers per rule and, for spacing/width
markers (edge pairs), the measured distances and where the markers are.

usage: lyrdb_summary.py <report.lyrdb> [max examples per rule, default 5]
"""
import collections
import re
import sys
import xml.etree.ElementTree as ET

NUM = r'(-?[0-9.]+(?:e-?[0-9]+)?)'
EDGE = re.compile(r'\(' + NUM + ',' + NUM + ';' + NUM + ',' + NUM + r'\)')


def seg_dist(a, b):
    """Smallest distance between two axis-parallel segments ((x1, y1), (x2, y2))."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    dx = max(0.0, max(min(ax1, ax2), min(bx1, bx2)) - min(max(ax1, ax2), max(bx1, bx2)))
    dy = max(0.0, max(min(ay1, ay2), min(by1, by2)) - min(max(ay1, ay2), max(by1, by2)))
    return (dx * dx + dy * dy) ** 0.5


def main(path, nex=5):
    items = ET.parse(path).getroot().find('items')
    items = list(items) if items is not None else []
    per = collections.defaultdict(list)
    for it in items:
        cat = (it.findtext('category') or '?').strip("'")
        vals = it.find('values')
        text = vals[0].text if vals is not None and len(vals) else ''
        edges = [((float(m[0]), float(m[1])), (float(m[2]), float(m[3]))) for m in EDGE.findall(text or '')]
        per[cat].append((text, edges))
    print(f"{path}: {len(items)} markers")
    for cat, lst in sorted(per.items(), key=lambda kv: -len(kv[1])):
        print(f"\n{cat}: {len(lst)}")
        dists = collections.Counter()
        xs, ys = [], []
        for _, edges in lst:
            if len(edges) == 2:
                dists[round(seg_dist(*edges), 3)] += 1
            for e in edges:
                for x, y in e:
                    xs.append(x)
                    ys.append(y)
        if dists:
            print("  distance (um): " + ', '.join(f"{d:g} x{n}" for d, n in sorted(dists.items())))
        if xs:
            print(f"  extent: x {min(xs):g}..{max(xs):g}, y {min(ys):g}..{max(ys):g}")
        for text, _ in lst[:nex]:
            print(f"  {text}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5)
