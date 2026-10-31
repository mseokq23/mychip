#!/usr/bin/env bash
# Starts the XFCE desktop in TigerVNC (:1) and the noVNC web client on $NO_VNC_PORT,
# using the startup script that ships inside IIC-OSIC-TOOLS. Safe to run again.
set -u

PORT="${NO_VNC_PORT:-6080}"
LOG=/tmp/iic-desktop.log

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; }

if port_open; then
  echo "[desktop] already running on port ${PORT}"
  exit 0
fi

if [ ! -x /dockerstartup/scripts/ui_startup.sh ]; then
  echo "[desktop] /dockerstartup/scripts/ui_startup.sh not found - is this the IIC-OSIC-TOOLS image?"
  exit 0
fi

export HOME=/headless          # the image keeps its desktop profile here (world-writable)
export DISPLAY=:1
export NO_VNC_PORT="${PORT}"
export XKB_KEYBOARD_LAYOUT="${XKB_KEYBOARD_LAYOUT:-us}"

# Detached from this shell so it survives the end of postStartCommand.
nohup setsid /dockerstartup/scripts/ui_startup.sh --vnc --wait >"${LOG}" 2>&1 </dev/null &

for _ in $(seq 1 90); do
  if port_open; then
    echo "[desktop] noVNC is up on port ${PORT}: Ports tab -> 'EDA Desktop (noVNC)', password ${VNC_PW:-abc123}"
    exit 0
  fi
  sleep 1
done

echo "[desktop] noVNC did not come up within 90 s. Last lines of ${LOG}:"
tail -n 40 "${LOG}" 2>/dev/null || true
exit 0   # never block the codespace start because of the desktop
