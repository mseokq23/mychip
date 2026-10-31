#!/usr/bin/env bash
# Fetches the open-source ETRI 0.5 um MPW design kit (GoodKook) with a sparse checkout
# (about 40 MB instead of ~4 GB) and wires it into Magic / KLayout / Xschem / ngspice / Netgen.
# Re-running it updates the kit. Options (environment variables):
#   ETRI050_WITH_DOCS=1   also fetch docs/ETRI_0p5um_NSPL_260820 (design rule PDFs, ~110 MB)
#   ETRI050_KIT_DIR=...   where to put the kit (default: <repo>/.pdk/ETRI050_DesignKit)
set -euo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT_REPO="${ETRI050_KIT_REPO:-https://github.com/GoodKook/ETRI-0.5um-CMOS-MPW-Std-Cell-DK.git}"
KIT_DIR="${ETRI050_KIT_DIR:-$WS/.pdk/ETRI050_DesignKit}"

DIRS=(tech spice scripts analog_ETRI digital_ETRI pads_ETRI sch lvs)
if [ "${ETRI050_WITH_DOCS:-0}" = "1" ]; then
  DIRS+=(docs/ETRI_0p5um_NSPL_260820)
fi

if [ ! -d "$KIT_DIR/.git" ]; then
  echo "[etri050] cloning design kit (sparse: ${DIRS[*]})"
  mkdir -p "$(dirname "$KIT_DIR")"
  git clone --quiet --depth 1 --filter=blob:none --sparse "$KIT_REPO" "$KIT_DIR"
  git -C "$KIT_DIR" sparse-checkout set "${DIRS[@]}"
else
  echo "[etri050] updating design kit"
  git -C "$KIT_DIR" sparse-checkout set "${DIRS[@]}"
  git -C "$KIT_DIR" pull --quiet --ff-only || echo "[etri050] pull skipped (local changes in the kit?)"
fi

# The kit's magicrc and scripts expect the kit at ~/ETRI050_DesignKit.
for h in "$HOME" /headless; do
  if [ -d "$h" ] && [ -w "$h" ]; then
    ln -sfn "$KIT_DIR" "$h/ETRI050_DesignKit"
  fi
done

# Helper commands (magic-etri, etri-drc, etri-lvs, ...) in every new bash terminal.
# Written as if/fi so it never returns an error: the desktop startup script sources
# ~/.bashrc under "set -e".
ENVF="$WS/scripts/etri050-env.sh"
LINE="if [ -f \"$ENVF\" ]; then source \"$ENVF\"; fi"
for rc in "$HOME/.bashrc" /headless/.bashrc; do
  if [ -e "$rc" ] || [ -w "$(dirname "$rc")" ]; then
    if [ -w "$rc" ] || [ ! -e "$rc" ]; then
      grep -qF "$LINE" "$rc" 2>/dev/null || echo "$LINE" >> "$rc"
    fi
  fi
done

mkdir -p "$WS/designs/etri050/netlist" "$WS/designs/tinytapeout"

echo "[etri050] kit:   $KIT_DIR ($(git -C "$KIT_DIR" log -1 --format='%h %cs'))"
echo "[etri050] model: $KIT_DIR/spice/05cmos_model_240201.lib"
echo "[etri050] open a new terminal, then try: magic-etri, klayout-etri, xschem-etri, etri-drc, etri-lvs"
