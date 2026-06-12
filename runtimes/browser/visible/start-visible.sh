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
CHROMIUM_START_URL="${CHROMIUM_START_URL:-about:blank}"
CHROMIUM_POLICY_DIR="${CHROMIUM_POLICY_DIR:-/etc/chromium/policies/managed}"
VISIBLE_BROWSER_MODE="${VISIBLE_BROWSER_MODE:-locked}"

mkdir -p \
  /tmp/.X11-unix \
  "${BROWSER_PROFILE_DIR}" \
  "${BROWSER_DOWNLOAD_DIR}"

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT TERM INT

Xvfb "${DISPLAY}" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -nolisten tcp &
pids+=("$!")

# Wait briefly for the X socket so Chromium does not race Xvfb startup.
x_socket="/tmp/.X11-unix/X${DISPLAY#:}"
for _ in $(seq 1 50); do
  [ -S "${x_socket}" ] && break
  sleep 0.1
done

case "${VISIBLE_BROWSER_MODE}" in
  locked)
    # Locked mode intentionally avoids a window manager, panels, menus, and
    # terminal affordances. noVNC sees only the X display containing Chromium.
    ;;
  desktop)
    fluxbox >/tmp/fluxbox.log 2>&1 &
    pids+=("$!")
    ;;
  *)
    echo "Unsupported VISIBLE_BROWSER_MODE=${VISIBLE_BROWSER_MODE}; expected 'locked' or 'desktop'" >&2
    exit 64
    ;;
esac

x11vnc -display "${DISPLAY}" -forever -shared -rfbport "${VNC_PORT}" -nopw -noxdamage >/tmp/x11vnc.log 2>&1 &
pids+=("$!")

websockify --web=/usr/share/novnc/ "${NOVNC_PORT}" "localhost:${VNC_PORT}" >/tmp/novnc.log 2>&1 &
pids+=("$!")

if [ -z "${CHROMIUM_BIN:-}" ]; then
  CHROMIUM_BIN="$(node -e "console.log(require('/opt/openquad/browser-runtime/node_modules/playwright').chromium.executablePath())")"
fi

chromium_flags=(
  "--remote-debugging-address=${CHROMIUM_CDP_HOST}"
  "--remote-debugging-port=${CHROMIUM_CDP_PORT}"
  "--user-data-dir=${BROWSER_PROFILE_DIR}"
  "--no-first-run"
  "--no-default-browser-check"
  "--disable-session-crashed-bubble"
  "--disable-dev-shm-usage"
  "--window-position=0,0"
  "--window-size=${SCREEN_WIDTH},${SCREEN_HEIGHT}"
)

if [ -n "${CHROMIUM_REMOTE_ALLOW_ORIGINS:-}" ]; then
  chromium_flags+=("--remote-allow-origins=${CHROMIUM_REMOTE_ALLOW_ORIGINS}")
fi

case "${VISIBLE_BROWSER_MODE}" in
  locked)
    chromium_flags+=(
      "--start-fullscreen"
      "--noerrdialogs"
      "--disable-infobars"
      "--disable-translate"
      "--disable-features=Translate"
    )
    ;;
  desktop)
    chromium_flags+=("--start-maximized")
    ;;
esac

if [ -n "${CHROMIUM_EXTRA_ARGS:-}" ]; then
  # shellcheck disable=SC2206
  extra_args=( ${CHROMIUM_EXTRA_ARGS} )
  chromium_flags+=("${extra_args[@]}")
fi

"${CHROMIUM_BIN}" "${chromium_flags[@]}" "${CHROMIUM_START_URL}" &
chromium_pid="$!"
pids+=("${chromium_pid}")

cat <<EOF
{"status":"ready","runtime":"${OPENQUAD_RUNTIME:-browser-runtime-visible}","mode":"${VISIBLE_BROWSER_MODE}","cdp":"http://${CHROMIUM_CDP_HOST}:${CHROMIUM_CDP_PORT}","vnc":"${VNC_PORT}","novnc":"${NOVNC_PORT}","policyDir":"${CHROMIUM_POLICY_DIR}","warning":"Treat CDP/VNC/noVNC as privileged browser-control access. Expose only inside the trusted network boundary."}
EOF

wait "${chromium_pid}"
