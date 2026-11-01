#!/usr/bin/env bash
# Installs the qflow digital flow that the ETRI 0.5 um kit uses, without root.
# The codespace user has no password-less sudo, so everything goes under one prefix:
#
#   tcsh      Ubuntu package, unpacked. qflow's scripts start with "#!/bin/tcsh -f";
#             the installed copies are pointed at this tcsh instead.
#   graywolf  placement: github.com/rubund/graywolf, as in the kit's Tools/graywolf_build.sh
#             (built with gcc; the kit script uses clang, which the image does not have)
#   qrouter   routing: github.com/RTimothyEdwards/qrouter tag 1.4.88, the version recorded in
#             the kit's latest fabricated layout (pong_pt1, MPW2025 STD-II; FIR_PE used 1.4.87)
#   qflow     the kit's Tools/qflow-1.4.100_etri050.tar.gz (qflow 1.4.100 plus tech/etri050),
#             installed as in Tools/qflow-1.4.100_etri050_build.sh, including the tech/etri050
#             links to the kit files
#
# Headers needed only for compiling (tcl8.6-dev, tk8.6-dev, libgsl-dev) are unpacked into
# <prefix>/sysroot. The programs run on the Tcl/Tk, GSL and X11 libraries already in the image
# (on 2026-11-01 the header packages had the same versions: Tcl/Tk 8.6.14, GSL 2.7.1).
#
# Usage:  bash scripts/install-qflow-etri050.sh     (a few minutes; finished parts are skipped)
#         ETRI050_TOOLS=<dir> changes the prefix (default ~/.local/etri050-tools)
# New terminals get <prefix>/bin on PATH through scripts/etri050-env.sh.
set -euo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="${ETRI050_TOOLS:-$HOME/.local/etri050-tools}"
KIT="${ETRI050_DK:-$WS/.pdk/ETRI050_DesignKit}"
[ -d "$KIT/.git" ] || KIT="$HOME/ETRI050_DesignKit"
GRAYWOLF_URL=https://github.com/rubund/graywolf.git
GRAYWOLF_REV=f47937b66d4d44eafc4224f7c43d556dbf88f05b   # master on 2026-11-01 (after tag 0.1.6)
QROUTER_URL=https://github.com/RTimothyEdwards/qrouter.git
QROUTER_REV=1.4.88
DEBS=(tcsh tcl8.6-dev tk8.6-dev libgsl-dev libgsl27 libgslcblas0)
ARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || echo x86_64-linux-gnu)"

SR="$P/sysroot"
SRC="$P/src"
LOG="$P/log"
mkdir -p "$P/bin" "$SR" "$SRC" "$LOG"
export PATH="$P/bin:$PATH"
J="$(nproc)"

say() { echo "[tools] $*"; }
die() { say "ERROR: $*"; exit 1; }
step() {   # step <name> <function>: runs it under set -e, output in log/<name>.log
  local name="$1" rc
  shift
  say "$name ..."
  set +e
  ( set -e; "$@" ) > "$LOG/$name.log" 2>&1
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    tail -25 "$LOG/$name.log"
    die "$name failed (full log: $LOG/$name.log)"
  fi
}

[ -f "$KIT/tech/etri050.sh" ] || die "kit not found at $KIT (run scripts/setup-etri050.sh first)"
for t in git gcc make cmake dpkg-deb apt-get tar python3 tclsh wish yosys magic netgen; do
  command -v "$t" >/dev/null 2>&1 || die "'$t' not found"
done

# 1. Ubuntu packages, downloaded and unpacked without root (apt index kept under the prefix)
packages() {
  local a="$P/apt" o d
  mkdir -p "$a/lists/partial" "$a/cache/archives/partial" "$P/debs"
  o=(-o "Dir::State::Lists=$a/lists" -o "Dir::Cache=$a/cache" -o Debug::NoLocking=1)
  apt-get "${o[@]}" update
  rm -f "$P"/debs/*.deb
  (cd "$P/debs" && apt-get "${o[@]}" download "${DEBS[@]}")
  for d in "$P"/debs/*.deb; do dpkg-deb -x "$d" "$SR"; done
  ls -1 "$P/debs"
}
if [ ! -x "$P/bin/tcsh" ]; then
  step packages packages
  TCSH="$(find "$SR" -path '*/bin/tcsh' -type f | head -1)"
  [ -n "$TCSH" ] || die "tcsh binary not found in the unpacked package"
  ln -sfn "$TCSH" "$P/bin/tcsh"
fi

# 2. graywolf
graywolf_build() {
  local s="$SRC/graywolf"
  [ -d "$s/.git" ] || git clone -q "$GRAYWOLF_URL" "$s"
  git -C "$s" checkout -q "$GRAYWOLF_REV"
  rm -rf "$s/build"
  mkdir "$s/build"
  cd "$s/build"
  PKG_CONFIG_PATH="$SR/usr/lib/$ARCH/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$SR" \
    cmake -DCMAKE_INSTALL_PREFIX="$P" \
          -DCMAKE_C_FLAGS="-fcommon -I$SR/usr/include" \
          -DCMAKE_EXE_LINKER_FLAGS="-L$SR/usr/lib/$ARCH" \
          -DCMAKE_SHARED_LINKER_FLAGS="-L$SR/usr/lib/$ARCH" ..
  make -j"$J"
  make install
}
if [ ! -x "$P/bin/graywolf" ]; then step graywolf graywolf_build; fi

# graywolf's own test suite (the kit script runs it too). The test scripts copy each case with
# "rsync <src> <dir>/ -a --copy-links -v"; the image has no rsync, so a stand-in doing the same
# copy (cp -RL) is put on PATH for the tests only. The cases compare placements with the
# expected files byte for byte. A failure is reported at the end, not fatal.
graywolf_test() {
  local b="$SRC/graywolf/build"
  mkdir -p "$b/shim"
  cat > "$b/shim/rsync" <<'EOF'
#!/bin/sh
src=; dst=
for a in "$@"; do case "$a" in -*) ;; *) if [ -z "$src" ]; then src=$a; else dst=$a; fi ;; esac; done
exec cp -RL "$src" "$dst"
EOF
  chmod +x "$b/shim/rsync"
  cd "$b"
  PATH="$b/shim:$PATH" ctest --output-on-failure || echo "graywolf: some tests failed"
}
if [ -d "$SRC/graywolf/build" ]; then step graywolf-test graywolf_test; fi

# 3. qrouter (Tcl/Tk headers and stub libraries from the sysroot, shared libraries from the image)
# Debian's /usr/lib/tk8.6/tkConfig.sh only sources /usr/lib/<arch>/tk8.6/tkConfig.sh by absolute
# path, which is not in the image, so the multiarch copies in the sysroot are named directly.
qrouter_build() {
  local s="$SRC/qrouter" tcl="$SR/usr/lib/$ARCH/tcl8.6" tk="$SR/usr/lib/$ARCH/tk8.6"
  [ -d "$s/.git" ] || git clone -q "$QROUTER_URL" "$s"
  git -C "$s" checkout -q "$QROUTER_REV"
  [ -f "$tcl/tclConfig.sh" ] || { echo "no tclConfig.sh in $tcl"; exit 1; }
  [ -f "$tk/tkConfig.sh" ] || { echo "no tkConfig.sh in $tk"; exit 1; }
  cd "$s"
  ./configure --prefix="$P" --with-tcl="$tcl" --with-tk="$tk" \
    --with-tclincls="$SR/usr/include/tcl8.6" --with-tkincls="$SR/usr/include/tcl8.6" \
    --with-tcllibs="/usr/lib/$ARCH" --with-tklibs="/usr/lib/$ARCH"
  make clean
  LDFLAGS="-L$SR/usr/lib/$ARCH" make
  make install
}
if [ ! -x "$P/bin/qrouter" ]; then step qrouter qrouter_build; fi

# 4. qflow-1.4.100_etri050 (configure records the graywolf, qrouter, yosys, magic and netgen it finds)
qflow_build() {
  local s="$SRC/qflow-1.4.100_etri050" t f
  rm -rf "$s"
  git -C "$KIT" show HEAD:Tools/qflow-1.4.100_etri050.tar.gz | tar xzf - -C "$SRC"
  cd "$s"
  ./configure --prefix="$P"
  make
  make install
  for f in "$P/bin/qflow" "$P"/share/qflow/scripts/*; do
    if head -1 "$f" | grep -q '^#!/bin/tcsh'; then sed -i "1s|^#!/bin/tcsh|#!$P/bin/tcsh|" "$f"; fi
  done
  # tech/etri050 -> kit files, the same links as Tools/qflow-1.4.100_etri050_build.sh
  t="$P/share/qflow/tech/etri050"
  rm -rf "$t.bak"
  mv "$t" "$t.bak"
  mkdir "$t"
  ln -s "$KIT/tech/SCN3ME_SUBM.30.ETRI.tech"           "$t/SCN3ME_SUBM.30.ETRI.tech"
  ln -s "$KIT/tech/etri050.par"                        "$t/etri050.par"
  ln -s "$KIT/tech/etri050.sh"                         "$t/etri050.sh"
  ln -s "$KIT/tech/etri050_setup.tcl"                  "$t/etri050_setup.tcl"
  ln -s "$KIT/digital_ETRI/khu_etri050.magicrc"        "$t/etri050.magicrc"
  ln -s "$KIT/digital_ETRI/khu_etri050.prm"            "$t/etri050.prm"
  ln -s "$KIT/digital_ETRI/etri050_stdcells.lef"       "$t/etri050_stdcells.lef"
  ln -s "$KIT/digital_ETRI/khu_etri050_stdcells.spice" "$t/etri050_stdcells.sp"
  ln -s "$KIT/digital_ETRI/khu_etri050_stdcells.gds2"  "$t/etri05_stdcells.gds2"
  ln -s "$KIT/digital_ETRI/khu_etri05_stdcells.lib"    "$t/etri05_stdcells.lib"
  ln -s "$KIT/digital_ETRI/khu_etri05_stdcells.v"      "$t/etri05_stdcells.v"
  for f in "$t"/*; do [ -e "$f" ] || { echo "missing kit file for $f"; exit 1; }; done
}
if [ ! -x "$P/bin/qflow" ]; then step qflow qflow_build; fi

say "done: $P/bin"
say "  tcsh     $("$P/bin/tcsh" --version | head -1)"
say "  graywolf $(git -C "$SRC/graywolf" describe --tags --always) (tests: $(grep -Eo '[0-9]+% tests passed.*' "$LOG/graywolf-test.log" 2>/dev/null | tail -1))"
say "  qrouter  $(cat "$SRC/qrouter/VERSION")"
say "  qflow    $(cat "$SRC/qflow-1.4.100_etri050/VERSION") (kit $(git -C "$KIT" log -1 --format=%h))"
say "open a new terminal (or: export PATH=\"$P/bin:\$PATH\"), then: cd designs/etri050/ctrl && make flow"
