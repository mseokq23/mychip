#!/usr/bin/env bash
# Build the PDK-layer cells (pnp10 copied from the kit, poly2 heater) and check each one with the
# kit's conversion of the official rule deck (KLayout). Output: designs/etri050/direct/build
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
KIT="${ETRI050_DK:-}"
[ -z "$KIT" ] && [ -d "$REPO/.pdk/ETRI050_DesignKit" ] && KIT="$REPO/.pdk/ETRI050_DesignKit"
[ -z "$KIT" ] && KIT="$HOME/ETRI050_DesignKit"
B="$HERE/build"
mkdir -p "$B"
export KLAYOUT_PATH="${KLAYOUT_HOME:-$HOME/.klayout}"
klayout -b -r "$HERE/pdk_cells.py" -rd kit="$KIT" -rd out="$B" "$@" > "$B/pdk_cells.log" 2>&1 \
  || { cat "$B/pdk_cells.log"; exit 1; }
grep -E '^(pnp10|heater):' "$B/pdk_cells.log"
for c in pnp10 heater; do
  rm -f "$B/${c}_klayout.lyrdb"
  klayout -b -r "$KIT/tech/Klayout_DRC_Script/etri_05um_generated_final.drc" \
    -rd gdsfile="$B/$c.gds" -rd resultsfile="$B/${c}_klayout.lyrdb" > "$B/${c}_klayout.log" 2>&1
  python3 "$REPO/scripts/lyrdb_summary.py" "$B/${c}_klayout.lyrdb" 2 > "$B/${c}_klayout.txt" 2>&1
  echo "-- $c: $(head -1 "$B/${c}_klayout.txt" | sed 's/.*: //')"
  grep -E '^[0-9A-Za-z_.]+: [0-9]+$|distance' "$B/${c}_klayout.txt"
done
