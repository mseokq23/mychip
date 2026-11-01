# shellcheck shell=bash
# ETRI 0.5 um (MyChip) helpers for IIC-OSIC-TOOLS.
# scripts/setup-etri050.sh adds "source <repo>/scripts/etri050-env.sh" to ~/.bashrc.
#
#   magic-etri [cell]                         Magic with the ETRI technology
#   klayout-etri [file.gds]                   KLayout with the ETRI layer colours
#   xschem-etri [file.sch]                    Xschem with designs/etri050/xschemrc
#   etri-drc <cell>                           Magic DRC of <cell>.mag (current directory)
#   etri-gds <cell>                           write <cell>.gds (ETRI layer numbers) from <cell>.mag
#   etri-gds-read <file.gds>                  import an ETRI GDS (e.g. from KLayout) into .mag cells
#   etri-drc-klayout <file.gds> [report]      KLayout DRC with the NSPL rule deck (v1.1)
#   etri-lvs <cell> <schematic.spice> [sub]   Magic extraction + Netgen LVS
#   etri-check <cell> [schematic.spice]       all of the above in one line: DRC x2, GDS, LVS

_etri_ws="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ETRI050_DK="${ETRI050_DK:-$_etri_ws/.pdk/ETRI050_DesignKit}"
export ETRI050_MODEL="${ETRI050_MODEL:-$ETRI050_DK/spice/05cmos_model_240201.lib}"
export ETRI050_MAGICRC="$ETRI050_DK/tech/etri050.magicrc"
export ETRI050_NETGEN_SETUP="$ETRI050_DK/tech/etri050_setup.tcl"
export ETRI050_DRC_DECK="$ETRI050_DK/tech/Klayout_DRC_Script/etri_05um_generated_final.drc"
export ETRI050_LYP="$ETRI050_DK/tech/ETRI050_CMOS.lyp"
export ETRI050_XSCHEMRC="$_etri_ws/designs/etri050/xschemrc"
export DISPLAY="${DISPLAY:-:1}"   # GUI programs open on the noVNC desktop

# qflow, graywolf, qrouter and tcsh installed without root by scripts/install-qflow-etri050.sh
_etri_tools="${ETRI050_TOOLS:-$HOME/.local/etri050-tools}/bin"
if [ -d "$_etri_tools" ] && [[ ":$PATH:" != *":$_etri_tools:"* ]]; then export PATH="$_etri_tools:$PATH"; fi

_etri_netgen() {
  if command -v netgen >/dev/null 2>&1; then netgen "$@"; else netgen-lvs "$@"; fi
}

# The image points KLAYOUT_PATH at the default PDK (IHP SG13G2): its technology and menus
# do not apply to ETRI layouts, so ETRI sessions use only the user's own KLayout folder.
_etri_klayout() { KLAYOUT_PATH="${KLAYOUT_HOME:-$HOME/.klayout}" klayout "$@"; }

magic-etri()   { magic -rcfile "$ETRI050_MAGICRC" "$@"; }
klayout-etri() { _etri_klayout -l "$ETRI050_LYP" -rm "$_etri_ws/scripts/klayout/etri_view.rb" "$@"; }
xschem-etri()  { xschem --rcfile "$ETRI050_XSCHEMRC" "$@"; }

etri-drc() {
  local cell="${1:?usage: etri-drc <cell>   (reads <cell>.mag in the current directory)}"
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" <<EOF
drc off
load ${cell} -force
select top cell
drc on
drc check
drc catchup
puts "ETRI-DRC ${cell}: [drc list count total] error(s)"
drc why
quit -noprompt
EOF
}

etri-gds() {
  local cell="${1:?usage: etri-gds <cell>   (writes <cell>.gds from <cell>.mag)}"
  # Magic's default output style uses MOSIS layer numbers; ETRI needs lambda=0.30(ETRI).
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" <<EOF
load ${cell} -force
cif ostyle lambda=0.30(ETRI)
gds write ${cell}.gds
quit -noprompt
EOF
}

etri-gds-read() {
  local gds="${1:?usage: etri-gds-read <file.gds>   (GDS with ETRI layer numbers -> .mag cells here)}"
  # For layouts made in KLayout / gdsfactory: import, then use etri-drc / etri-lvs on the top cell.
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" <<EOF
cif istyle lambda=0.30(ETRI)
gds read ${gds}
writeall force
quit -noprompt
EOF
}

etri-drc-klayout() {
  local gds="${1:?usage: etri-drc-klayout <file.gds> [report.lyrdb]}"
  local rpt="${2:-${gds%.gds}_drc.lyrdb}"
  _etri_klayout -b -r "$ETRI050_DRC_DECK" -rd gdsfile="$gds" -rd resultsfile="$rpt"
  echo "report: $rpt   (view with: klayout-etri $gds -m $rpt)"
}

etri-lvs() {
  local usage="usage: etri-lvs <cell> <schematic.spice> [schematic_subckt]"
  local cell="${1:?$usage}" sch="${2:?$usage}" sub="${3:-$1}" lay out="${1}_lvs.out" verdict
  # Extraction writes <cell>.spice next to <cell>.mag: keep the schematic netlist elsewhere.
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" >"${cell}_ext.log" 2>&1 <<EOF
load ${cell} -force
extract all
ext2spice lvs
ext2spice
quit -noprompt
EOF
  # A cell with ports is written as ".subckt <cell> <pins>", and Netgen also compares the pins.
  # Without ports the netlist is a bare top level: only devices and nets can be compared.
  if grep -qiE "^\.subckt[[:space:]]+${cell}([[:space:]]|$)" "${cell}.spice"; then
    lay="${cell}.spice ${cell}"
  else
    lay="${cell}.spice"
    echo "note: ${cell} has no ports, so pin names are not compared (Magic: box over the cell, then 'port makeall')"
  fi
  _etri_netgen -batch lvs "$lay" "${sch} ${sub}" "$ETRI050_NETGEN_SETUP" "$out" >/dev/null
  if grep -qE "do not match|failed pin matching|with port errors" "$out"; then
    verdict="MISMATCH"
  elif grep -qE "Circuits match|Netlists match" "$out"; then
    verdict="MATCH"
    if grep -qE "Property errors were found|There were property errors" "$out"; then
      verdict="MATCH but property errors (W, L, ...)"
    fi
  else
    verdict="no result"
  fi
  echo "ETRI-LVS ${cell}: ${verdict}   (details: ${out})"
}

_etri_lyrdb_count() {   # number of markers in a KLayout report database, "?" if unreadable
  python3 - "$1" 2>/dev/null <<'PY' || echo "?"
import sys, xml.etree.ElementTree as ET
items = ET.parse(sys.argv[1]).getroot().find("items")
print(0 if items is None else len(items))
PY
}

etri-check() {
  local usage="usage: etri-check <cell> [schematic.spice] [subckt]   (Magic DRC, ETRI GDS, KLayout DRC, LVS)"
  local cell="${1:?$usage}" sch="${2:-}" sub="${3:-$1}" ndrc nkl lvs="-" bad=0
  ndrc=$(etri-drc "$cell" 2>/dev/null | sed -n 's/^ETRI-DRC [^:]*: \([0-9][0-9]*\) error.*/\1/p')
  [ "$ndrc" = "0" ] || bad=1
  etri-gds "$cell" >"${cell}_gds.log" 2>&1
  rm -f "${cell}_drc.lyrdb"
  etri-drc-klayout "${cell}.gds" "${cell}_drc.lyrdb" >"${cell}_klayout.log" 2>&1
  nkl=$(_etri_lyrdb_count "${cell}_drc.lyrdb")
  [ "$nkl" = "0" ] || bad=1
  if [ -n "$sch" ]; then
    lvs=$(etri-lvs "$cell" "$sch" "$sub" 2>/dev/null | sed -n 's/^ETRI-LVS [^:]*: \(.*\)   (details.*/\1/p')
    [ "$lvs" = "MATCH" ] || bad=1
  fi
  echo "ETRI-CHECK ${cell}: Magic DRC ${ndrc:-?} | KLayout DRC ${nkl} | LVS ${lvs:-?}"
  return "$bad"
}
