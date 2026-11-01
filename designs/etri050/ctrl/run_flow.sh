#!/usr/bin/env bash
# Place and route teg_ctrl with qflow and the ETRI 0.5 um open-source kit.
# The steps are those of the kit's RTL_Project/ETRI050 Makefile (synthesize, place, sta,
# route, migrate, lvs) followed by the kit's layout checks (run_drc.sh, run_lvs.sh,
# check_via_stack.py), i.e. the flow used for the FIR_PE chip (MPW240925002).
#
# Work directory: build/qflow (recreated each run). qflow finds the technology in
# build/qflow/tech/etri050, which links the kit files under the names tech/etri050.sh expects.
# Summary: build/qflow/flow_summary.txt
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
KIT="${ETRI050_DK:-}"
[ -z "$KIT" ] && [ -d "$REPO/.pdk/ETRI050_DesignKit" ] && KIT="$REPO/.pdk/ETRI050_DesignKit"
[ -z "$KIT" ] && KIT="$HOME/ETRI050_DesignKit"
TOP=teg_ctrl
W="$HERE/build/qflow"

die() { echo "[flow] ERROR: $*" >&2; exit 1; }
[ -f "$KIT/tech/etri050.sh" ] || die "kit not found at $KIT (run scripts/setup-etri050.sh)"
TOOLS="${ETRI050_TOOLS:-$HOME/.local/etri050-tools}"
if [ -d "$TOOLS/bin" ]; then PATH="$TOOLS/bin:$PATH"; fi
for t in qflow yosys graywolf qrouter magic netgen tcsh; do
  command -v "$t" >/dev/null 2>&1 || die "'$t' not found in PATH (install: bash scripts/install-qflow-etri050.sh)"
done

echo "[flow] kit: $KIT ($(git -C "$KIT" log -1 --format='%h %cs' 2>/dev/null || echo unknown))"
echo "[flow] tools: qflow $(command -v qflow) | $(yosys -V 2>&1 | head -1) | magic $(magic --version 2>/dev/null) | qrouter $(qrouter -v 0 -h 2>&1 | grep -o 'version [0-9.A-Za-z]*' | head -1)"

rm -rf "$W"
mkdir -p "$W"/{source,synthesis,layout,log,tech/etri050}
cp "$HERE/$TOP/$TOP.v" "$W/source/"

# technology directory: the same links as the kit's Tools/qflow-1.4.100_etri050_build.sh
# (qflow copies etri050.magicrc to layout/.magicrc; it is the kit template's layout/.magicrc)
T="$W/tech/etri050"
ln -s "$KIT/tech/SCN3ME_SUBM.30.ETRI.tech"           "$T/SCN3ME_SUBM.30.ETRI.tech"
ln -s "$KIT/tech/etri050.par"                        "$T/etri050.par"
ln -s "$KIT/tech/etri050.sh"                         "$T/etri050.sh"
ln -s "$KIT/tech/etri050_setup.tcl"                  "$T/etri050_setup.tcl"
ln -s "$KIT/digital_ETRI/khu_etri050.magicrc"        "$T/etri050.magicrc"
ln -s "$KIT/digital_ETRI/khu_etri050.prm"            "$T/etri050.prm"
ln -s "$KIT/digital_ETRI/etri050_stdcells.lef"       "$T/etri050_stdcells.lef"
ln -s "$KIT/digital_ETRI/khu_etri050_stdcells.spice" "$T/etri050_stdcells.sp"
ln -s "$KIT/digital_ETRI/khu_etri050_stdcells.gds2"  "$T/etri05_stdcells.gds2"
ln -s "$KIT/digital_ETRI/khu_etri05_stdcells.lib"    "$T/etri05_stdcells.lib"
ln -s "$KIT/digital_ETRI/khu_etri05_stdcells.v"      "$T/etri05_stdcells.v"
for f in "$T"/*; do [ -e "$f" ] || die "missing kit file for $(basename "$f")"; done
export QFLOW_TECH_DIR="$T"

# project settings and placement parameters from the kit template; pin sides from this design
cp "$KIT/scripts/RTL_Project/ETRI050/project_vars.sh"        "$W/project_vars.sh"
echo 'set route_show = 0   # batch run: no qrouter display window' >> "$W/project_vars.sh"
cp "$KIT/scripts/RTL_Project/ETRI050/layout/TOP_MODULE.par"  "$W/layout/$TOP.par"
cp "$HERE/layout/$TOP.cel2"                                  "$W/layout/$TOP.cel2"

cd "$W" || die "cannot enter $W"
step() {   # step <name> <command...>
  local name="$1"; shift
  echo "[flow] $name"
  if "$@" > "log/step_$name.out" 2>&1; then echo "[flow] $name: ok"; return 0; fi
  echo "[flow] $name: FAILED (log/step_$name.out)"; tail -20 "log/step_$name.out"; return 1
}
step synthesize qflow synthesize -T etri050 "$TOP" || exit 1
step place      qflow place      -T etri050 "$TOP" || exit 1
step sta        qflow sta        -T etri050 "$TOP" || echo "[flow] sta skipped (timing is not a sign-off item here)"
step route      qflow route      -T etri050 "$TOP" || exit 1
step migrate    qflow migrate    -T etri050 "$TOP" || exit 1
bash "$KIT/scripts/fix_net_name.sh" "synthesis/$TOP.spc" > /dev/null
step lvs        qflow lvs        -T etri050 "$TOP" || echo "[flow] qflow lvs reported a problem"

# kit layout checks (same scripts as the FIR_PE submission)
cd layout || die "no layout directory"
bash "$KIT/scripts/run_drc.sh" "$TOP" > "${TOP}_DRC.log" 2>&1
bash "$KIT/scripts/run_lvs.sh" "$TOP" > "${TOP}_LVS.log" 2>&1
python3 "$KIT/scripts/check_via_stack.py" "$TOP" m2contact m3contact 6 > "${TOP}_Stacked.log" 2>&1
magic -dnull -noconsole > "${TOP}_size.log" 2>&1 << EOF
drc off
box 0 0 0 0
load $TOP.mag -force
select top cell
box
quit -noprompt
EOF
cd ..

{
  echo "teg_ctrl qflow run $(date '+%Y-%m-%d %H:%M')"
  echo "-- synthesis"; grep -E -i 'Number of cells|cells:' log/synth.log | tail -3
  echo "-- route";     grep -E -i 'Final:|Failed|unrouted|routed' log/route.log | tail -5
  echo "-- qflow lvs"; grep -E -i 'match|Result' log/lvs.log | tail -3
  echo "-- kit DRC";   grep -E -i 'error|count' "layout/${TOP}_DRC.log" | tail -5
  echo "-- kit LVS";   grep -E -i 'Circuit 1 contains|Circuit 2 contains|match' "layout/LVS_${TOP}.txt" 2>/dev/null | tail -6
  echo "-- via stack"; tail -3 "layout/${TOP}_Stacked.log"
  echo "-- size";      grep -E 'microns|lambda' "layout/${TOP}_size.log" | tail -2
} | tee flow_summary.txt
