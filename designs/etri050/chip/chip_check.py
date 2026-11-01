"""Check the wiring of pdkv_Top on its metal: each intended net is one piece of metal and nothing else
is joined (KLayout batch mode).

Reads <build>/pdkv_nets.json from assemble.py: the blocks placed (GDS, position) and, for every net
the routing makes, probe points on the pad port and on the block pins it must reach. Connectivity is
extracted on MET1, VIA1, MET2, VIA2 and MET3 only, so a transistor, a diode or a resistor never joins
its terminals and the result says what the metal alone connects.

  1. every probe point of a net lies on one extracted net (opens);
  2. the metal nets of each block alone (pad ring, seal ring, control block, L-split, MOS-C, PNPs, heater,
     Kelvin array, CBCM block, RO bank, resistor RO) are extracted too, and one point of each is probed in
     the chip: a chip net that holds block nets must hold exactly the block nets that one intended net
     was drawn to join, i.e. the block nets under that net's probe points (shorts between nets, between
     two nets of one block, or into a block net no probe declares, such as a node inside the array);
  3. metal the routing added that touches no block is reported (floating pieces);
  4. every vertex of the chip lies on the 0.01 um design grid (rule document 3.3; ETRI's Calibre
     deck checks OFFGRID per layer, the kit KLayout deck does not);
  5. star nets (pdkv_nets.json 'star'): the chip is extracted again without the joint block (VSS: the
     pad ring, whose PVSS pad joins the branches) and the probe points of each branch of the net must be
     one net, and no two branches one net: the heater's return current and the PNP1 / L-split ground
     share no metal with the core's ground.

The control block, the L-split, the MOS-C, the array, the CBCM block, the RO bank and the resistor RO
also pass their own LVS (qflow/kit Netgen, etri-check; the resistor RO also at device level with its
POLY2 resistors, ro/rores_lvs.py); the GPIO cells, pnp10 and the heater are ETRI or PDK layout with
pins only, as in the kit's flow.

usage: klayout -b -r designs/etri050/chip/chip_check.py -rd nets=<build>/pdkv_nets.json
"""
import json
import pya

LAYERS = (('m1', 32), ('v1', 33), ('m2', 34), ('v2', 35), ('m3', 36))


def extract(ly, cell):
    ly.flatten(cell.cell_index(), -1, True)      # one circuit: every net is a net of the cell itself
    l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, cell, []))
    regs = {}
    for name, n in LAYERS:
        li = ly.find_layer(n, 0)
        if li is None:
            li = ly.layer(n, 0)
        regs[name] = l2n.make_layer(li, name)
    for a, b in (('m1', 'v1'), ('v1', 'm2'), ('m2', 'v2'), ('v2', 'm3')):
        l2n.connect(regs[a])
        l2n.connect(regs[a], regs[b])
    l2n.connect(regs['m3'])
    l2n.extract_netlist()
    return l2n, regs


def probe(l2n, regs, layer, x, y):
    net = l2n.probe_net(regs[layer], pya.DPoint(x, y))
    return net.cluster_id if net is not None else None


def inner_points(l2n, regs, dbu):
    """One point inside the metal of every net of a block (the vertex mean of a convex piece)."""
    circuit = next(l2n.netlist().each_circuit_top_down())
    out = []
    for net in circuit.each_net():
        for name in ('m1', 'm2', 'm3'):
            shapes = l2n.shapes_of_net(net, regs[name], True)
            if shapes.is_empty():
                continue
            poly = next(iter(shapes.each()))
            piece = poly.decompose_convex()[0] if not poly.is_box() else poly
            pts = list(piece.each_point()) if hasattr(piece, 'each_point') else list(piece.each_point_hull())
            x = sum(p.x for p in pts) / len(pts) * dbu
            y = sum(p.y for p in pts) / len(pts) * dbu
            out.append((net.cluster_id, name, x, y))
            break
    return out


def off_grid(ly, cell, grid_um=0.01):
    g = int(round(grid_um / ly.dbu))
    count = {}
    for li in ly.layer_indexes():
        it = cell.begin_shapes_rec(li)
        while not it.at_end():
            shape = it.shape()
            if shape.is_box() or shape.is_polygon() or shape.is_path():
                poly = shape.polygon.transformed(it.trans())
                n = sum((p.x % g != 0) + (p.y % g != 0) for p in poly.each_point_hull())
                for h in range(poly.holes()):
                    n += sum((p.x % g != 0) + (p.y % g != 0) for p in poly.each_point_hole(h))
                if n:
                    info = ly.get_info(li)
                    count[f'{info.layer}/{info.datatype}'] = count.get(f'{info.layer}/{info.datatype}', 0) + n
            it.next()
    return count


def main(spec_file):
    spec = json.load(open(spec_file))
    top_ly = pya.Layout()
    top_ly.read(spec['top'])
    top_cell = top_ly.top_cell()
    grid = off_grid(top_ly, top_cell)
    print(f"  0.01 um grid: {sum(grid.values())} off-grid coordinates" + (f" {grid}" if grid else ''))
    bad = (sum(grid.values()) > 0)
    l2n, regs = extract(top_ly, top_cell)
    dbu = top_ly.dbu

    # 1. opens
    expected_members = {}
    probe_net_of = {}
    for net, probes in spec['nets'].items():
        ids = {probe(l2n, regs, p['layer'], p['x'], p['y']) for p in probes}
        ok = len(ids) == 1 and None not in ids
        bad += not ok
        probe_net_of[net] = ids
        print(f"  {net:4s} {len(probes):2d} points: {'one net' if ok else 'OPEN ' + str(sorted(map(str, ids)))}")
        if not ok:
            for p in probes:
                print(f"         {p['at']}: net {probe(l2n, regs, p['layer'], p['x'], p['y'])}")

    # 2. block nets probed in the chip
    members = {}          # chip net -> list of (block, block net)
    cache = {}
    for b in spec['blocks']:
        if b['gds'] not in cache:
            bl = pya.Layout()
            bl.read(b['gds'])
            bl2n, bregs = extract(bl, bl.top_cell())
            cache[b['gds']] = (bl2n, bregs, inner_points(bl2n, bregs, bl.dbu))
        t = pya.DCplxTrans(1, b['rot'], b['mirror'], b['x'], b['y'])
        lost = 0
        for nid, layer, x, y in cache[b['gds']][2]:
            p = t * pya.DPoint(x, y)
            cid = probe(l2n, regs, layer, p.x, p.y)
            if cid is None:
                lost += 1
                continue
            members.setdefault(cid, []).append((b['name'], nid))
        print(f"  block {b['name']}: {len(cache[b['gds']][2])} metal nets probed" + (f", {lost} not found" if lost else ''))
        bad += lost
    # the block nets each intended net was drawn to join: the ones under its probe points
    for net, probes in spec['nets'].items():
        drawn = set()
        for p in probes:
            for b in spec['blocks']:
                bl2n, bregs, _ = cache[b['gds']]
                q = pya.DCplxTrans(1, b['rot'], b['mirror'], b['x'], b['y']).inverted() * pya.DPoint(p['x'], p['y'])
                nid = probe(bl2n, bregs, p['layer'], q.x, q.y)
                if nid is not None:
                    drawn.add((b['name'], nid))
        expected_members[net] = drawn
    owner = {}
    for net, mem in expected_members.items():
        for m in mem:
            owner[m] = net
    shorts = 0
    for cid, mem in members.items():
        intended = [n for n in spec['nets'] if probe_net_of[n] == {cid}]
        if len(mem) < 2 and not intended:
            continue
        nets_here = {owner.get(m) for m in mem}
        if len(intended) != 1 or nets_here != {intended[0]} or set(mem) != expected_members[intended[0]]:
            shorts += 1
            if len(intended) == 1:       # one intended net: name the block nets its probes do not account for
                what, shown = 'not drawn to be joined', set(mem) - expected_members[intended[0]]
            else:
                what, shown = 'block nets', set(mem)
            names = sorted(f'{blk}:{nid}' for blk, nid in shown)
            print(f"  SHORT on chip net {cid}: {len(mem)} block nets, {what}: "
                  f"{names[:8]}{' ...' if len(names) > 8 else ''} (intended net: {intended or 'none'})")
    bad += shorts

    # 3. floating route metal (chip nets without any block net)
    floating = [n for n in next(l2n.netlist().each_circuit_top_down()).each_net() if n.cluster_id not in members]
    flo = 0
    for n in floating:
        area = sum(l2n.shapes_of_net(n, regs[k], True).area() for k in ('m1', 'm2', 'm3'))
        if area > 0:
            flo += 1
            box = pya.Region()
            for k in ('m1', 'm2', 'm3'):
                box += l2n.shapes_of_net(n, regs[k], True)
            print(f"  FLOATING metal: {box.bbox().to_dtype(dbu)}")
    bad += flo

    # 5. star nets: branches that may meet only inside one block (VSS: in the PVSS pad)
    star_bad = 0
    for st in spec.get('star', []):
        jb = next(b for b in spec['blocks'] if b['name'] == st['joint'])
        jl = pya.Layout()
        jl.read(jb['gds'])
        sl = pya.Layout()
        sl.read(spec['top'])
        stop = sl.top_cell()
        gone = [i for i in stop.each_inst() if i.cell.name == jl.top_cell().name]
        for i in gone:
            i.delete()
        sl2n, sregs = extract(sl, stop)
        branch = {}
        for p in spec['nets'][st['net']]:
            if 'branch' in p:
                branch.setdefault(p['branch'], []).append((p['at'], probe(sl2n, sregs, p['layer'], p['x'], p['y'])))
        owner, shared = {}, {}
        for name, pts in branch.items():
            for _, i in pts:
                if i is not None and owner.setdefault(i, name) != name:
                    shared.setdefault(i, {owner[i]}).add(name)
        apart = not shared
        for i, names in shared.items():
            print(f"  star {st['net']}: branches {sorted(names)} share net {i} without {st['joint']}")
        problems = len(gone) != 1
        for name, pts in branch.items():
            ids = {i for _, i in pts}
            one = len(ids) == 1 and None not in ids
            problems += not one
            print(f"  star {st['net']} without {st['joint']}: branch '{name}' {len(pts)} points: "
                  f"{'one net ' + str(next(iter(ids))) if one else 'NOT ONE NET ' + str(sorted(map(str, ids)))}")
            if not one:
                for at, i in pts:
                    print(f"         {at}: net {i}")
        problems += not apart
        print(f"  star {st['net']}: {len(branch)} branches meet only in {st['joint']} -> "
              f"{'ok' if not problems else 'JOINED OUTSIDE IT' if not apart else 'PROBLEM'}"
              + (f" ({len(gone)} instances of {st['joint']} removed)" if len(gone) != 1 else ''))
        star_bad += problems > 0
    bad += star_bad
    print(f"chip check: {len(spec['nets'])} nets, {sum(len(v) for v in spec['nets'].values())} points, "
          f"{shorts} shorts, {flo} floating pieces, {sum(grid.values())} off-grid coordinates, "
          f"{len(spec.get('star', [])) - star_bad} of {len(spec.get('star', []))} star nets apart -> "
          f"{'PASS' if bad == 0 else f'{bad} problem(s)'}")


main(globals().get('nets') or 'pdkv_nets.json')
