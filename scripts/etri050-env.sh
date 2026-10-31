# shellcheck shell=bash
# ETRI 0.5 um (MyChip) helpers for IIC-OSIC-TOOLS.
# scripts/setup-etri050.sh adds "source <repo>/scripts/etri050-env.sh" to ~/.bashrc.
#
#   magic-etri [cell]                         Magic with the ETRI technology
#   klayout-etri [file.gds]                   KLayout with the ETRI layer colours
#   xschem-etri [file.sch]                    Xschem with designs/etri050/xschemrc
#   etri-drc <cell>                           Magic DRC of <cell>.mag (current directory)
#   etri-gds <cell>                           write <cell>.gds from <cell>.mag
#   etri-drc-klayout <file.gds> [report]      KLayout DRC with the NSPL rule deck (v1.1)
#   etri-lvs <cell> <schematic.spice> [sub]   Magic extraction + Netgen LVS

_etri_ws="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ETRI050_DK="${ETRI050_DK:-$_etri_ws/.pdk/ETRI050_DesignKit}"
export ETRI050_MODEL="${ETRI050_MODEL:-$ETRI050_DK/spice/05cmos_model_240201.lib}"
export ETRI050_MAGICRC="$ETRI050_DK/tech/etri050.magicrc"
export ETRI050_NETGEN_SETUP="$ETRI050_DK/tech/etri050_setup.tcl"
export ETRI050_DRC_DECK="$ETRI050_DK/tech/Klayout_DRC_Script/etri_05um_generated_final.drc"
export ETRI050_LYP="$ETRI050_DK/tech/ETRI050_CMOS.lyp"
export ETRI050_XSCHEMRC="$_etri_ws/designs/etri050/xschemrc"
export DISPLAY="${DISPLAY:-:1}"   # GUI programs open on the noVNC desktop

_etri_netgen() {
  if command -v netgen >/dev/null 2>&1; then netgen "$@"; else netgen-lvs "$@"; fi
}

magic-etri()   { magic -rcfile "$ETRI050_MAGICRC" "$@"; }
klayout-etri() { klayout -l "$ETRI050_LYP" "$@"; }
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
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" <<EOF
load ${cell} -force
gds write ${cell}.gds
quit -noprompt
EOF
}

etri-drc-klayout() {
  local gds="${1:?usage: etri-drc-klayout <file.gds> [report.lyrdb]}"
  local rpt="${2:-${gds%.gds}_drc.lyrdb}"
  klayout -b -r "$ETRI050_DRC_DECK" -rd gdsfile="$gds" -rd resultsfile="$rpt"
  echo "report: $rpt   (view with: klayout-etri $gds -m $rpt)"
}

etri-lvs() {
  local usage="usage: etri-lvs <cell> <schematic.spice> [schematic_subckt]"
  local cell="${1:?$usage}" sch="${2:?$usage}" sub="${3:-$1}"
  # Extraction writes <cell>.spice next to <cell>.mag: keep the schematic netlist elsewhere.
  magic -dnull -noconsole -rcfile "$ETRI050_MAGICRC" <<EOF
load ${cell} -force
extract all
ext2spice lvs
ext2spice subcircuit top off
ext2spice
quit -noprompt
EOF
  _etri_netgen -batch lvs "${cell}.spice ${cell}" "${sch} ${sub}" "$ETRI050_NETGEN_SETUP" "${cell}_lvs.out" >/dev/null
  grep -E "Netlists match|Netlists do not match|Circuits match|do not match" "${cell}_lvs.out" | tail -n 2
  echo "details: ${cell}_lvs.out"
}
