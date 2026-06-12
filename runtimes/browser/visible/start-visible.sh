#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
SCREEN_WIDTH="${SCREEN_WIDTH:-1440}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-1000}"
SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
CHROMIUM_CDP_HOST="${CHROMIUM_CDP_HOST:-0.0.0.0}"
CHROMIUM_CDP_PORT="${CHROMIUM_CDP_PORT:-9222}"
BROWSER_PROFILE_DIR="${BROWSER_PROFILE_DIR:-/home/pwuser/browser-profile}"
BROWSER_DOWNLOAD_DIR="${BROWSER_DOWNLOAD_DIR:-/home/pwuser/downloads}"

mkdir -p "${BROWSER_PROFILE_DIR}" "${BROWSER_DOWNLOAD_DIR}"

Xvfb "${DISPLAY}" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -nolisten tcp &
xvfb_pid="$!"

fluxbox >/tmp/fluxbox.log 2>&1 &
fluxbox_pid="$!"

x11vnc -display "${DISPLAY}" -forever -shared -rfbport "${VNC_PORT}" -nopw >/tmp/x11vnc.log 2>&1 &
x11vnc_pid="$!"

websockify --web=/usr/share/novnc/ "${NOVNC_PORT}" "localhost:${VNC_PORT}" >/tmp/novnc.log 2>&1 &
novnc_pid="$!"

cleanup() {
  kill "${novnc_pid}" "${x11vnc_pid}" "${fluxbox_pid}" "${xvfb_pid}" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

if [ -z "${CHROMIUM_BIN:-}" ]; then
  CHROMIUM_BIN="$(node -e "console.log(require('/opt/openquad/browser-runtime/node_modules/playwright').chromium.executablePath())")"
fi

"${CHROMIUM_BIN}" \
  --remote-debugging-address="${CHROMIUM_CDP_HOST}" \
  --remote-debugging-port="${CHROMIUM_CDP_PORT}" \
  --user-data-dir="${BROWSER_PROFILE_DIR}" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --window-size="${SCREEN_WIDTH},${SCREEN_HEIGHT}" \
  "${CHROMIUM_START_URL:-about:blank}" &
chromium_pid="$!"

echo "{\"status\":\"ready\",\"runtime\":\"${OPENQUAD_RUNTIME:-browser-runtime-visible}\",\"cdp\":\"http://${CHROMIUM_CDP_HOST}:${CHROMIUM_CDP_PORT}\",\"vnc\":\"${VNC_PORT}\",\"novnc\":\"${NOVNC_PORT}\",\"warning\":\"Treat CDP/VNC/noVNC as privileged browser-control access. Expose only inside the trusted network boundary.\"}"

wait "${chromium_pid}"
