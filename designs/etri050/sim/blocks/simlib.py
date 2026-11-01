"""Common helpers for the block checks: PDK model setup and an ngspice runner.

Models: the official NSPL PDK (05cmos_model_260210.lib for diode/BJT/resistor sections and
05cmos_mosfet_corner.lib for TT/SS/FF/SF/FS MOS corners). They are taken from the PDK archive
in the kit (docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz) and never copied into
the repository. The kit standard-cell netlist is mapped to the PDK device names
(nfet/pfet -> nmos4/pmos4).
"""
import os
import re
import shutil
import subprocess
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
BUILD = os.path.join(HERE, 'build')
MODELS = ('05cmos_model_260210.lib', '05cmos_mosfet_corner.lib')


def kit_dir():
    for p in (os.environ.get('ETRI050_DK'), os.path.join(REPO, '.pdk', 'ETRI050_DesignKit'),
              os.path.expanduser('~/ETRI050_DesignKit')):
        if p and os.path.isdir(p):
            return p
    raise SystemExit('ETRI kit not found: run scripts/setup-etri050.sh')


def setup():
    """Put the PDK models and the mapped standard-cell netlist into build/."""
    os.makedirs(BUILD, exist_ok=True)
    if not all(os.path.exists(os.path.join(BUILD, f)) for f in MODELS):
        src = os.environ.get('ETRI050_PDK_MODELS')
        if src:
            for f in MODELS:
                shutil.copy(os.path.join(src, f), BUILD)
        else:
            tgz = os.path.join(kit_dir(), 'docs', 'ETRI_0p5um_NSPL_260820', 'NSPL_05CMOS_PDK_260820.tar.gz')
            if not os.path.exists(tgz):
                raise SystemExit('PDK model archive not found. Fetch the kit docs with\n'
                                 '  ETRI050_WITH_DOCS=1 bash scripts/setup-etri050.sh\n'
                                 'or set ETRI050_PDK_MODELS to a folder holding ' + ' and '.join(MODELS))
            with tarfile.open(tgz) as t:
                for m in t.getmembers():
                    if m.isfile() and os.path.basename(m.name) in MODELS:
                        m.name = os.path.basename(m.name)
                        t.extract(m, BUILD)
    # One ngspice thread per run: the block scripts run one ngspice per core, and ngspice's own
    # OpenMP threads (2 by default) then oversubscribe the cores. Two runs at once on 2 cores took
    # 9 min each instead of 11 s (2026-11-01); the results are the same.
    init = os.path.join(BUILD, '.spiceinit')
    if not os.path.exists(init):
        open(init, 'w').write('set num_threads=1\n')
    cells = os.path.join(BUILD, 'stdcells.spice')
    if not os.path.exists(cells):
        txt = open(os.path.join(kit_dir(), 'digital_ETRI', 'khu_etri050_stdcells.spice')).read()
        txt = re.sub(r'\bnfet\b', 'nmos4', txt)
        txt = re.sub(r'\bpfet\b', 'pmos4', txt)
        open(cells, 'w').write(txt)


def header(corner='TT', temp=27, extra='', reltol='1e-4', method='', abstol='1e-15'):
    opts = f'.options gmin=1e-15 abstol={abstol} reltol={reltol}' + (f' method={method}' if method else '')
    return (f"* block check\n.lib '05cmos_mosfet_corner.lib' {corner}\n.include 'stdcells.spice'\n"
            f"{opts}\n.temp {temp}\n{extra}\n")


def run(net, name):
    """Run ngspice in batch mode inside build/. Lines 'RES k=v ...' are returned as a dict."""
    setup()
    path = os.path.join(BUILD, name + '.cir')
    open(path, 'w').write(net)
    r = subprocess.run(['ngspice', '-b', path], cwd=BUILD, capture_output=True, text=True, timeout=3600)
    out = r.stdout + r.stderr
    open(os.path.join(BUILD, name + '.log'), 'w').write(out)
    res = {}
    for line in out.splitlines():
        if line.startswith('RES '):
            for k, v in re.findall(r'(\S+?)=(\S+)', line[4:]):
                try:
                    res[k] = float(v)
                except ValueError:
                    res[k] = v
    return res


def geo(w, sd=2.1):
    """Source/drain junction area and perimeter for a single-finger device of width w (um)."""
    return f"ad={w * sd:.2f}p as={w * sd:.2f}p pd={2 * w + 2 * sd:.2f}u ps={2 * w + 2 * sd:.2f}u"


def p2res(temp, squares, rsh=125.0, tc1=3.915e-4, tc2=3.647e-6, tnom=27.0):
    """Poly2 resistor body value from the PDK p2res model (contacts excluded)."""
    dt = temp - tnom
    return rsh * squares * (1 + tc1 * dt + tc2 * dt * dt)
