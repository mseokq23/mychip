#!/usr/bin/env bash
# Build the pdkv pad ring and check it against the kit's own template ring.
#   1. pad_ring.py: kit 28-pin GPIO template -> build/pdkv_Pad.mag (+ build/pad_pins.json)
#   2. Magic writes both rings to GDS with the kit's GPIO style lambda=0.30(ETRI-G), as the kit's
#      generate_chip.sh does for <chip>_Pad (the GPIO cells came from ETRI's GDS)
#   3. KLayout DRC with the kit's conversion of the official rule deck on both rings;
#      markers that the template ring also has belong to the ETRI GPIO cells, not to this design
# Usage: bash run_pad_ring.sh [--force-port PADR]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
KIT="${ETRI050_DK:-}"
[ -z "$KIT" ] && [ -d "$REPO/.pdk/ETRI050_DesignKit" ] && KIT="$REPO/.pdk/ETRI050_DesignKit"
[ -z "$KIT" ] && KIT="$HOME/ETRI050_DesignKit"
B="$HERE/build"
mkdir -p "$B"
python3 "$HERE/pad_ring.py" --kit "$KIT" --outdir "$B" "$@" > "$B/pad_ring.log" 2>&1 \
  || { cat "$B/pad_ring.log"; exit 1; }
head -2 "$B/pad_ring.log"
cp "$KIT/pads_ETRI/MPW_PAD_28Pin_IO.mag" "$B/template_Pad.mag"

cd "$B" || exit 1
for cell in pdkv_Pad template_Pad; do
  rm -f "$cell.gds" "${cell}_klayout.lyrdb"
  magic -dnull -noconsole -rcfile "$KIT/tech/etri050.magicrc" > "${cell}_gds.log" 2>&1 << EOF
drc off
box 0 0 0 0
addpath $KIT/pads_ETRI
addpath $KIT/pads_ETRI/GDS_Magic
load $cell
select top cell
expand
box
cif ostyle lambda=0.30(ETRI-G)
gds write $cell
quit -noprompt
EOF
  if [ ! -f "$cell.gds" ]; then echo "[pad ring] $cell.gds not written (see $B/${cell}_gds.log)"; exit 1; fi
  KLAYOUT_PATH="${KLAYOUT_HOME:-$HOME/.klayout}" klayout -b -r "$KIT/tech/Klayout_DRC_Script/etri_05um_generated_final.drc" \
    -rd gdsfile="$cell.gds" -rd resultsfile="${cell}_klayout.lyrdb" > "${cell}_klayout.log" 2>&1
  python3 "$REPO/scripts/lyrdb_summary.py" "${cell}_klayout.lyrdb" 0 > "${cell}_klayout.txt" 2>&1
done
{
  echo "pdkv pad ring $(date '+%Y-%m-%d %H:%M')"
  for cell in pdkv_Pad template_Pad; do
    echo "-- $cell: $(grep -c "^use " "$cell.mag") instances, missing cells: $(grep -ci "could not find\|not found" "${cell}_gds.log")"
    grep -E 'microns' "${cell}_gds.log" | tail -1
    grep -E 'markers|^[0-9A-Za-z_.]+: [0-9]+$' "${cell}_klayout.txt"
  done
} | tee "$B/pad_ring_summary.txt"
