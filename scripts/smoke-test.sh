#!/usr/bin/env bash
# End-to-end check of the IIC-OSIC-TOOLS + ETRI 0.5 um setup.
# Draws a small NMOS (W/L = 3/0.6 um) and runs every step of the flow on it:
# tools, kit files, ngspice, Xschem, Magic DRC, GDS layer numbers, KLayout DRC, LVS, desktop.
# Usage: bash scripts/smoke-test.sh     (outputs in /tmp/etri050-smoke, or set SMOKE_DIR)
set -u

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/etri050-env.sh
source "$WS/scripts/etri050-env.sh"
OUT="${SMOKE_DIR:-/tmp/etri050-smoke}"
mkdir -p "$OUT" && cd "$OUT" || exit 1
rm -rf ./smoke_nmos* ./nmos_tb.spice ./sch ./*.log

npass=0; nwarn=0; nfail=0
pass() { printf 'PASS  %s\n' "$1"; npass=$((npass + 1)); }
warn() { printf 'WARN  %s\n' "$1"; nwarn=$((nwarn + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; nfail=$((nfail + 1)); }

# 1. tools ------------------------------------------------------------------
for t in magic klayout xschem ngspice python3; do
  if command -v "$t" >/dev/null 2>&1; then pass "tool $t"; else fail "tool $t not found"; fi
done
if command -v netgen >/dev/null 2>&1 || command -v netgen-lvs >/dev/null 2>&1; then
  pass "tool netgen"
else
  fail "tool netgen not found"
fi
printf 'INFO  magic %s | %s | %s\n' "$(magic --version 2>/dev/null)" \
  "$(klayout -v 2>/dev/null)" "$(xschem --version 2>/dev/null | head -n 1)"

# 2. kit files --------------------------------------------------------------
for f in "$ETRI050_MAGICRC" "$ETRI050_MODEL" "$ETRI050_NETGEN_SETUP" "$ETRI050_DRC_DECK" "$ETRI050_LYP"; do
  if [ -f "$f" ]; then pass "kit file ${f#"$ETRI050_DK"/}"; else fail "kit file missing: $f"; fi
done
if [ -d "$HOME/ETRI050_DesignKit/tech" ]; then
  pass "kit link ~/ETRI050_DesignKit (used by the kit's magicrc)"
else
  fail "$HOME/ETRI050_DesignKit missing (run: bash scripts/setup-etri050.sh)"
fi

# 3. ngspice example: Vt(20/20 um) at 27 C should be near the 0.70 V target --
# (ngspice-47 drops the spaces around "=" in echo output, older versions keep them)
line=$(cd "$WS/designs/etri050/sim" && ngspice -b nmos_idvg.spice 2>/dev/null | grep -E '^T ?= ?27 ')
vt=$(printf '%s' "$line" | sed -n 's/.*Vt(20\/20) *= *\([-0-9.eE+]*\) V.*/\1/p')
if [ -n "$vt" ] && awk -v v="$vt" 'BEGIN { exit !(v > 0.60 && v < 0.80) }'; then
  pass "ngspice example: Vt(20/20) = $vt V at 27 C"
else
  fail "ngspice example (got: '${line:-nothing}')"
fi

# 4. Xschem: netlist the example testbench in batch mode, then simulate it ----
if xschem -x -q -n -s --rcfile "$ETRI050_XSCHEMRC" -o "$OUT" \
     "$WS/designs/etri050/sch/nmos_tb.sch" >xschem.log 2>&1 && [ -f "$OUT/nmos_tb.spice" ]; then
  xvt=$(ngspice -b "$OUT/nmos_tb.spice" 2>/dev/null | sed -n 's/^Vt .* = \([-0-9.eE+]*\) V$/\1/p')
  if [ -n "$xvt" ]; then pass "xschem netlist + ngspice: Vt = $xvt V"; else fail "xschem netlist ran without a Vt result"; fi
else
  fail "xschem netlisting (see $OUT/xschem.log)"
fi

# 5. Magic: draw the test transistor (labels made into ports), then DRC --------
magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" >magic_build.log 2>&1 <<'EOF'
load smoke_nmos
box 0um 0um 5.4um 3.0um
paint ndiffusion
box 0um 0.6um 1.8um 2.4um
paint ndcontact
label S
box 3.6um 0.6um 5.4um 2.4um
paint ndcontact
label D
box 2.4um -0.6um 3.0um 3.6um
paint polysilicon
box 1.8um 3.6um 3.6um 5.4um
paint polycontact
label G
box 7.2um 0.6um 9.0um 2.4um
paint psubstratepcontact
label B
box -1um -1um 10um 6um
port makeall
save smoke_nmos
quit -noprompt
EOF
drc_line=$(etri-drc smoke_nmos 2>/dev/null | grep 'ETRI-DRC smoke_nmos')
drc_n=$(printf '%s' "$drc_line" | sed -n 's/.*: \([0-9]*\) error.*/\1/p')
if [ "$drc_n" = "0" ]; then
  pass "Magic DRC: 0 errors"
else
  fail "Magic DRC (${drc_line:-no result}; see $OUT/magic_build.log)"
fi

# 6. GDS export must use ETRI layer numbers (ACT 11, POLY1 12, CONT 31) ------
etri-gds smoke_nmos >gds.log 2>&1
layers=$(python3 - smoke_nmos.gds 2>/dev/null <<'PY'
import sys
try:
    import klayout.db as db
    ly = db.Layout()
    ly.read(sys.argv[1])
    top = ly.top_cell()
    found = {(ly.get_info(i).layer, ly.get_info(i).datatype) for i in ly.layer_indexes()
             if not top.bbox_per_layer(i).empty()}
except ImportError:
    import gdstk
    lib = gdstk.read_gds(sys.argv[1])
    found = {(p.layer, p.datatype) for c in lib.cells for p in c.polygons}
print(" ".join(f"{l}/{d}" for l, d in sorted(found)))
PY
)
if [[ " $layers " == *" 11/0 "* && " $layers " == *" 12/0 "* && " $layers " == *" 31/0 "* ]]; then
  pass "GDS layers (ETRI numbers): $layers"
else
  fail "GDS layers: '${layers:-unreadable}' (expected 11/0, 12/0, 31/0)"
fi

# 7. KLayout DRC with the kit's NSPL rule deck --------------------------------
etri-drc-klayout smoke_nmos.gds smoke_nmos_drc.lyrdb >klayout_drc.log 2>&1
if [ -f smoke_nmos_drc.lyrdb ]; then
  summary=$(python3 - smoke_nmos_drc.lyrdb <<'PY'
import sys, collections, xml.etree.ElementTree as ET
items = ET.parse(sys.argv[1]).getroot().find("items")
count = collections.Counter((it.findtext("category") or "?").strip("'") for it in
                            (items if items is not None else []))
print(sum(count.values()), " ".join(f"{k}:{v}" for k, v in sorted(count.items())))
PY
)
  nk=${summary%% *}
  if [ "$nk" = "0" ]; then
    pass "KLayout DRC: 0 violations"
  else
    warn "KLayout DRC: $nk marker(s) by rule: ${summary#* }"
  fi
else
  fail "KLayout DRC did not run (see $OUT/klayout_drc.log)"
fi

# 8. LVS: extracted layout vs. schematic netlist (devices, W/L and pins) ------
mkdir -p sch
cat > sch/smoke_nmos.spice <<'EOF'
* schematic netlist for the smoke-test transistor
.subckt smoke_nmos D G S B
M1 D G S B nfet W=3u L=0.6u
.ends
EOF
lvs=$(etri-lvs smoke_nmos sch/smoke_nmos.spice smoke_nmos 2>/dev/null)
if printf '%s' "$lvs" | grep -qE 'ETRI-LVS smoke_nmos: MATCH +\(details' &&
   grep -q 'Cell pin lists are equivalent' smoke_nmos_lvs.out; then
  pass "LVS: devices, W/L and pins match"
else
  fail "LVS: $(printf '%s' "$lvs" | tail -n 1)"
fi

# 9. noVNC desktop ------------------------------------------------------------
if (exec 3<>"/dev/tcp/127.0.0.1/${NO_VNC_PORT:-6080}") 2>/dev/null; then
  pass "noVNC desktop listening on port ${NO_VNC_PORT:-6080}"
else
  fail "noVNC desktop not listening (run: bash .devcontainer/start-desktop.sh)"
fi

echo
echo "SMOKE TEST: ${npass} passed, ${nwarn} warning(s), ${nfail} failed"
echo "outputs: $OUT   (layout view: klayout-etri $OUT/smoke_nmos.gds)"
[ "$nfail" -eq 0 ]
