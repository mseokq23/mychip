#!/usr/bin/env bash
# Assemble pdkv_Top and check it.
#   1. inputs, built when missing: pad ring (run_pad_ring.sh), lsplit + mosc (etri050_direct.py),
#      pnp10 + heater (run_pdk_cells.sh); the control block is the frozen macro in ctrl/macro
#   2. assemble.py -> build/pdkv_Top.gds + build/pdkv_nets.json
#   3. the kit's conversion of the official rule deck (KLayout) on the whole chip
#   4. chip_check.py: metal connectivity (opens, shorts, floating metal) and the 0.01 um grid
# Usage: bash run_chip.sh [--rebuild]   (--rebuild remakes the inputs too)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
KIT="${ETRI050_DK:-}"
[ -z "$KIT" ] && [ -d "$REPO/.pdk/ETRI050_DesignKit" ] && KIT="$REPO/.pdk/ETRI050_DesignKit"
[ -z "$KIT" ] && KIT="$HOME/ETRI050_DesignKit"
export KLAYOUT_PATH="${KLAYOUT_HOME:-$HOME/.klayout}"
B="$HERE/build"
D="$REPO/designs/etri050/direct/build"
mkdir -p "$B"
REBUILD=0; [ "${1:-}" = "--rebuild" ] && REBUILD=1

if [ $REBUILD = 1 ] || [ ! -f "$B/pdkv_Pad.gds" ]; then bash "$HERE/run_pad_ring.sh" > /dev/null || exit 1; fi
if [ $REBUILD = 1 ] || [ ! -f "$D/lsplit.gds" ] || [ ! -f "$D/mosc.gds" ]; then
  python3 "$REPO/designs/etri050/gen/etri050_direct.py" > "$B/direct.log" 2>&1 || { cat "$B/direct.log"; exit 1; }
fi
if [ $REBUILD = 1 ] || [ ! -f "$D/pnp10.gds" ] || [ ! -f "$D/heater.gds" ]; then
  bash "$REPO/designs/etri050/direct/run_pdk_cells.sh" > /dev/null || exit 1
fi

t0=$(date +%s)
klayout -b -r "$HERE/assemble.py" -rd repo="$REPO" > "$B/assemble.log" 2>&1 || { cat "$B/assemble.log"; exit 1; }
rm -f "$B/pdkv_Top_klayout.lyrdb"
klayout -b -r "$KIT/tech/Klayout_DRC_Script/etri_05um_generated_final.drc" \
  -rd gdsfile="$B/pdkv_Top.gds" -rd resultsfile="$B/pdkv_Top_klayout.lyrdb" > "$B/pdkv_Top_klayout.log" 2>&1
python3 "$REPO/scripts/lyrdb_summary.py" "$B/pdkv_Top_klayout.lyrdb" 2 > "$B/pdkv_Top_klayout.txt" 2>&1
klayout -b -r "$HERE/chip_check.py" -rd nets="$B/pdkv_nets.json" > "$B/chip_check.log" 2>&1
{
  echo "pdkv chip $(date '+%Y-%m-%d %H:%M'), kit $(git -C "$KIT" log -1 --format=%h 2>/dev/null || echo unknown), $(( $(date +%s) - t0 )) s"
  grep -E '^wrote' "$B/assemble.log"
  echo "-- KLayout DRC, official rules (pdkv_Top.gds)"
  grep -E 'markers|^[0-9A-Za-z_.]+: [0-9]+$' "$B/pdkv_Top_klayout.txt"
  echo "-- chip check (metal connectivity, grid)"
  grep -E 'grid|OPEN|SHORT|FLOATING|not found|chip check' "$B/chip_check.log"
} | tee "$B/chip_summary.txt"
