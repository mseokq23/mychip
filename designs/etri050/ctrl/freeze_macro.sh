#!/usr/bin/env bash
# Freeze the routed control block as the macro the chip assembly reads (after run_flow.sh):
#   macro/teg_ctrl.gds.gz      build/qflow/layout/teg_ctrl_F_grid.gds: flat, notches filled,
#                              snapped to the 0.01 um grid, official-rule KLayout DRC 0
#   macro/teg_ctrl_pins.txt    pin rectangles from the labels of the qflow layout (teg_ctrl.mag,
#                              magscale 1 4 = 0.075 um), before snapping; assemble.py rounds them
#                              the way snap_grid.py rounded the GDS
#   macro/teg_ctrl.v           the gate netlist placed and routed (build/qflow/synthesis/
#                              teg_ctrl.rtlnopwr.v, after qflow's post-placement buffering; the
#                              netlist make qflowsim simulates)
#   macro/teg_ctrl.spc         its teg_ctrl subcircuit as qflow's LVS read it (synthesis/teg_ctrl.spc
#                              without the kit cell library it includes); chip/chip_lvs.py compares
#                              the macro inside the chip with it at device level
# The chip is assembled from the frozen macro, so a later qflow run cannot move its pins unnoticed.
# Compare a new run with the macro first: klayout -b -r scripts/gds_xor.py -rd a=... -rd b=...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L="$HERE/build/qflow/layout"
S="$HERE/build/qflow/synthesis"
[ -f "$L/teg_ctrl_F_grid.gds" ] || { echo "run run_flow.sh first ($L/teg_ctrl_F_grid.gds missing)"; exit 1; }
mkdir -p "$HERE/macro"
gzip -9 -n -c "$L/teg_ctrl_F_grid.gds" > "$HERE/macro/teg_ctrl.gds.gz"
cp "$S/teg_ctrl.rtlnopwr.v" "$HERE/macro/teg_ctrl.v"
sed -n '/^\.subckt teg_ctrl /,$p' "$S/teg_ctrl.spc" > "$HERE/macro/teg_ctrl.spc"
{
  echo '# teg_ctrl pins: name layer x1 y1 x2 y2 (um, coordinates of GDS cell teg_ctrl_F before the 0.01 um snap; flabels of qflow layout/teg_ctrl.mag, 1 unit = 0.075 um)'
  awk '$1=="flabel"{o=($3=="s")?1:0; printf "%s %s %.3f %.3f %.3f %.3f\n", $(NF), $2, $(3+o)*0.075, $(4+o)*0.075, $(5+o)*0.075, $(6+o)*0.075}' \
    "$L/teg_ctrl.mag" | sort -k1,1V
} > "$HERE/macro/teg_ctrl_pins.txt"
echo "macro: $(ls -l "$HERE/macro/teg_ctrl.gds.gz" | awk '{print $5}') bytes, $(($(wc -l < "$HERE/macro/teg_ctrl_pins.txt") - 1)) pins, $(grep -c '^X' "$HERE/macro/teg_ctrl.spc") cells"
