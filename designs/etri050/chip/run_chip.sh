#!/usr/bin/env bash
# Assemble pdkv_Top and check it.
#   1. inputs, built when missing: pad ring (run_pad_ring.sh), lsplit + mosc (etri050_direct.py),
#      pnp10 + heater (run_pdk_cells.sh), Kelvin array (etri050_array.py); the control block is the
#      frozen macro in ctrl/macro
#   2. assemble.py -> build/pdkv_Top.gds + build/pdkv_nets.json, with the chip boundary (layer 0) and
#      the seal ring of rule document 4.21 unless PDKV_SEAL=0
#   3. the kit's conversion of the official rule deck (KLayout) on the whole chip
#   4. scripts/metal_rules.py: rules 7-12 with the rule document's values (via spacing 0.8 um, the
#      deck uses 0.5) and the seal ring against the 4.21 figure, markers also found in the pad ring
#      alone counted apart
#   5. chip_check.py: metal connectivity (opens, shorts, floating metal) and the 0.01 um grid
#   6. scripts/antenna_rules.py: the rule document's antenna rules (3.PL1/8.MET1/10.MET2/12.MET3.ANT)
# Usage: [PDKV_SEAL=0] bash run_chip.sh [--rebuild]   (--rebuild remakes the inputs too)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
KIT="${ETRI050_DK:-}"
[ -z "$KIT" ] && [ -d "$REPO/.pdk/ETRI050_DesignKit" ] && KIT="$REPO/.pdk/ETRI050_DesignKit"
[ -z "$KIT" ] && KIT="$HOME/ETRI050_DesignKit"
export KLAYOUT_PATH="${KLAYOUT_HOME:-$HOME/.klayout}"
B="$HERE/build"
D="$REPO/designs/etri050/direct/build"
A="$REPO/designs/etri050/array/build"
mkdir -p "$B"
REBUILD=0; [ "${1:-}" = "--rebuild" ] && REBUILD=1

if [ $REBUILD = 1 ] || [ ! -f "$B/pdkv_Pad.gds" ]; then bash "$HERE/run_pad_ring.sh" > /dev/null || exit 1; fi
if [ $REBUILD = 1 ] || [ ! -f "$D/lsplit.gds" ] || [ ! -f "$D/mosc.gds" ]; then
  python3 "$REPO/designs/etri050/gen/etri050_direct.py" > "$B/direct.log" 2>&1 || { cat "$B/direct.log"; exit 1; }
fi
if [ $REBUILD = 1 ] || [ ! -f "$D/pnp10.gds" ] || [ ! -f "$D/heater.gds" ]; then
  bash "$REPO/designs/etri050/direct/run_pdk_cells.sh" > /dev/null || exit 1
fi
if [ $REBUILD = 1 ] || [ ! -f "$A/karray.gds" ] || [ ! -f "$A/karray_pins.json" ]; then
  mkdir -p "$A"
  python3 "$REPO/designs/etri050/gen/etri050_array.py" > "$A/array.log" 2>&1 || { cat "$A/array.log"; exit 1; }
fi

t0=$(date +%s)
klayout -b -r "$HERE/assemble.py" -rd repo="$REPO" -rd seal="${PDKV_SEAL:-1}" > "$B/assemble.log" 2>&1 || { cat "$B/assemble.log"; exit 1; }
rm -f "$B/pdkv_Top_klayout.lyrdb"
klayout -b -r "$KIT/tech/Klayout_DRC_Script/etri_05um_generated_final.drc" \
  -rd gdsfile="$B/pdkv_Top.gds" -rd resultsfile="$B/pdkv_Top_klayout.lyrdb" > "$B/pdkv_Top_klayout.log" 2>&1
python3 "$REPO/scripts/lyrdb_summary.py" "$B/pdkv_Top_klayout.lyrdb" 2 > "$B/pdkv_Top_klayout.txt" 2>&1
klayout -b -r "$REPO/scripts/metal_rules.py" -rd gds="$B/pdkv_Top.gds" -rd baseline="$B/pdkv_Pad.gds" \
  > "$B/pdkv_Top_metal_rules.txt" 2>&1
klayout -b -r "$HERE/chip_check.py" -rd nets="$B/pdkv_nets.json" > "$B/chip_check.log" 2>&1
klayout -b -r "$REPO/scripts/antenna_rules.py" -rd gds="$B/pdkv_Top.gds" -rd nets="$B/pdkv_nets.json" \
  > "$B/pdkv_Top_antenna.txt" 2>&1
{
  echo "pdkv chip $(date '+%Y-%m-%d %H:%M'), kit $(git -C "$KIT" log -1 --format=%h 2>/dev/null || echo unknown), $(( $(date +%s) - t0 )) s"
  grep -E '^wrote' "$B/assemble.log"
  echo "-- KLayout DRC, official rules (pdkv_Top.gds)"
  grep -E 'markers|^[0-9A-Za-z_.]+: [0-9]+$' "$B/pdkv_Top_klayout.txt"
  echo "-- rules 7-12 and seal ring 4.21, rule document values (baseline: pad ring alone)"
  cat "$B/pdkv_Top_metal_rules.txt"
  echo "-- chip check (metal connectivity, grid)"
  grep -E 'grid|OPEN|SHORT|FLOATING|not found|chip check' "$B/chip_check.log"
  echo "-- antenna, rule document v1.1 (ratio per gate type, no diode credit; 'diffusion': the net reaches a junction)"
  cat "$B/pdkv_Top_antenna.txt"
} | tee "$B/chip_summary.txt"
