#!/bin/bash
# shellcheck disable=SC2016 # Single-quoted commands expand in the container.
set -Eeuo pipefail
engine=${CONTAINER_ENGINE:-docker}
kind=${1:?chatgpt or hermes required}
image=${2:?image required}
case "$kind" in chatgpt|hermes) ;; *) exit 64 ;; esac
# Pin the test contract independently from the production Shell image. The
# checked-out tree supplies the viewer, stream driver, and geometry verifier.
shell_revision=${PELAGIAN_SHELL_CONFORMANCE_COMMIT:-8b36c276549a89fc04de4accd84672add9d77ac3}
shell_source=$(mktemp -d)
git -C "$shell_source" init -q
git -C "$shell_source" fetch -q --depth 1 https://github.com/Pelagians/pelagian-shell.git "$shell_revision"
test "$(git -C "$shell_source" rev-parse FETCH_HEAD)" = "$shell_revision"
git -C "$shell_source" checkout -q --detach FETCH_HEAD
conformance="$shell_source/tests/consumer-conformance"
name="grotto-${kind}-desktop-smoke-$$"
volumes=(workspace tools homebrew cache)
config_mount=${GROTTO_CONFIG_BIND:-${name}-config}
if [[ -n "${GROTTO_CONFIG_BIND:-}" ]]; then
    config_mount="${GROTTO_CONFIG_BIND}:/config:Z"
else
    volumes+=(config)
    config_mount="${name}-config:/config"
fi
# shellcheck disable=SC2317,SC2329
cleanup() {
    result=$?
    trap - EXIT
    if (( result != 0 )); then
        "$engine" logs "$name" >&2 || true
        # The container shell expands diagnostic paths.
        # shellcheck disable=SC2016
        "$engine" exec "$name" sh -c 'for f in /config/.local/state/pelagian-shell/*.log /config/hermes-desktop/session.log /config/hermes-desktop/hermes-home/logs/desktop.log /tmp/hermes-window-chrome.json; do test ! -f "$f" || { echo "--- $f"; tail -n 80 "$f"; }; done; for f in /tmp/pelagian-layout-second.pid /tmp/pelagian-layout-second.display /tmp/pelagian-layout-second.log; do test ! -f "$f" || { echo "--- $f"; cat "$f"; }; done; echo "--- runtime sockets"; ls -la /run/pelagian-shell 2>&1 || true; echo "--- layoutd status"; pelagian-layoutd status 2>&1 || true; echo "--- Wayland toplevels"; wlrctl toplevel list 2>&1 || true' >&2 || true
    fi
    "$engine" rm -f "$name" >/dev/null 2>&1 || true
    for volume in "${volumes[@]}"; do
        "$engine" volume rm -f "${name}-${volume}" >/dev/null 2>&1 || true
    done
    rm -rf "$shell_source"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
for volume in "${volumes[@]}"; do
    "$engine" volume create "${name}-${volume}" >/dev/null
done
if [[ "${GROTTO_EXPECT_CONFIG_PERSISTENCE:-false}" == true ]]; then
    "$engine" run --rm --entrypoint sh --volume "$config_mount" "$image" -c \
        'test "$(cat /config/consumer-volume-sentinel)" = preserved'
else
    "$engine" run --rm --entrypoint sh --volume "$config_mount" "$image" -c \
        'mkdir -p /config/.codex; printf preserved > /config/consumer-volume-sentinel'
fi
# Exercise the real /init entrypoint. Login uses no real accounts in CI.
consumer_env=()
if [[ "$kind" == hermes ]]; then
    consumer_env+=(--env HERMES_DESKTOP_WINDOW_CHROME_REPORT=/tmp/hermes-window-chrome.json)
fi
"$engine" run -d --name "$name" --shm-size=2g \
    --env "PUID=$(id -u)" --env "PGID=$(id -g)" \
    --env GROTTO_CHATGPT_AUTH_MODE=off \
    --env GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD=ci-ephemeral-keyring \
    --env SELKIES_MANUAL_WIDTH=1920 --env SELKIES_MANUAL_HEIGHT=1080 \
    "${consumer_env[@]}" \
    --volume "$config_mount" --volume "${name}-workspace:/workspace" \
    --volume "${name}-tools:/tools" --volume "${name}-homebrew:/home/linuxbrew/.linuxbrew" \
    --volume "${name}-cache:/cache" "$image" >/dev/null
"$engine" cp "$conformance/verify-shell-session.py" "$name:/tmp/verify-shell-session.py"
"$engine" cp "$shell_source/tests/layout-fixture.py" "$name:/tmp/grotto-shell-layout-fixture.py"
"$engine" exec "$name" chmod 0644 /tmp/verify-shell-session.py /tmp/grotto-shell-layout-fixture.py

get_main_window_pid() {
    "$engine" exec -i "$name" python3 - "$kind" <<'PY'
import json
import socket
import sys

pattern = sys.argv[1]
with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(3)
    client.connect('/run/pelagian-shell/labwc.sock')
    client.sendall(b'LIST\n')
    chunks = []
    while chunk := client.recv(65536):
        chunks.append(chunk)
state = json.loads(b''.join(chunks))
windows = [
    view for view in state['views']
    if view['type'] == 'normal' and view['parent_id'] is None
    and pattern in (view['app_id'] + ' ' + view['title']).lower()
]
if len(windows) == 1:
    print(windows[0]['pid'])
PY
}

labwc_has_second_fixture() {
    "$engine" exec -i --user abc "$name" python3 - <<'PY'
import json
import socket
import sys

with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(3)
    client.connect('/run/pelagian-shell/labwc.sock')
    client.sendall(b'LIST\n')
    chunks = []
    while chunk := client.recv(65536):
        chunks.append(chunk)
state = json.loads(b''.join(chunks))
sys.exit(0 if any(view['title'] == 'Pelagian Fixture Two' for view in state['views']) else 1)
PY
}

verify_two_window_dialog_and_reflow() {
    "$engine" exec --user abc "$name" /usr/bin/python3 -c \
        'import gi; gi.require_version("Gtk", "3.0")'

    session_wayland_display=''
    fixture_pid=''
    available_displays=$("$engine" exec "$name" sh -c '
for socket in /run/pelagian-shell/wayland-*; do
    test -S "$socket" || continue
    printf "%s\n" "$(basename "$socket")"
done
')
    while IFS= read -r display; do
        [[ -n "$display" ]] || continue
        "$engine" exec "$name" rm -f \
            /tmp/pelagian-layout-second.pid \
            /tmp/pelagian-layout-second.display \
            /tmp/pelagian-layout-second.log \
            /tmp/pelagian-layout-second.command \
            /tmp/pelagian-layout-second.ack
        "$engine" exec -d --user abc \
            --env GDK_BACKEND=wayland \
            --env XDG_RUNTIME_DIR=/run/pelagian-shell \
            --env WAYLAND_DISPLAY="$display" \
            --env DBUS_SESSION_BUS_ADDRESS=unix:path=/run/pelagian-shell/bus \
            "$name" sh -c \
            'exec /usr/bin/python3 /tmp/grotto-shell-layout-fixture.py second > /tmp/pelagian-layout-second.log 2>&1'

        for _ in $(seq 1 100); do
            fixture_pid=$("$engine" exec "$name" cat /tmp/pelagian-layout-second.pid 2>/dev/null || true)
            if [[ -n "$fixture_pid" ]] \
                && "$engine" exec "$name" kill -0 "$fixture_pid" >/dev/null 2>&1 \
                && labwc_has_second_fixture >/dev/null 2>&1; then
                fixture_display=$("$engine" exec "$name" cat /tmp/pelagian-layout-second.display)
                if [[ "$fixture_display" == "$display" ]]; then
                    session_wayland_display=$display
                    break
                fi
            fi
            sleep 0.1
        done
        [[ -n "$session_wayland_display" ]] && break
        if [[ -n "$fixture_pid" ]]; then
            "$engine" exec "$name" kill "$fixture_pid" >/dev/null 2>&1 || true
        fi
    done <<< "$available_displays"
    if [[ -z "$session_wayland_display" ]]; then
        echo 'GTK fixture did not appear in Labwc on any Shell Wayland socket' >&2
        "$engine" exec "$name" sh -c \
            'test ! -f /tmp/pelagian-layout-second.log || cat /tmp/pelagian-layout-second.log' >&2 || true
        return 1
    fi
    printf 'GTK fixture connected to Labwc on %s\n' "$session_wayland_display"

    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py \
        "$kind" --managed-count 2 --floating-count 0

    "$engine" exec --user abc "$name" sh -c \
        'printf dialog > /tmp/pelagian-layout-second.command'
    acknowledged=false
    for _ in $(seq 1 100); do
        ack=$("$engine" exec "$name" cat /tmp/pelagian-layout-second.ack 2>/dev/null || true)
        if [[ "$ack" == dialog ]]; then
            acknowledged=true
            break
        fi
        sleep 0.1
    done
    [[ "$acknowledged" == true ]]
    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py \
        "$kind" --managed-count 2 --floating-count 1

    "$engine" exec --user abc "$name" sh -c \
        'printf dialog-close > /tmp/pelagian-layout-second.command'
    acknowledged=false
    for _ in $(seq 1 100); do
        ack=$("$engine" exec "$name" cat /tmp/pelagian-layout-second.ack 2>/dev/null || true)
        if [[ "$ack" == dialog-close ]]; then
            acknowledged=true
            break
        fi
        sleep 0.1
    done
    [[ "$acknowledged" == true ]]
    fixture_pid=$("$engine" exec "$name" cat /tmp/pelagian-layout-second.pid)
    "$engine" exec "$name" kill "$fixture_pid"
    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py \
        "$kind" --managed-count 1
}

verify_hermes_window_chrome() {
    [[ "$kind" == hermes ]] || return 0

    for _ in $(seq 1 100); do
        report=$("$engine" exec "$name" cat /tmp/hermes-window-chrome.json 2>/dev/null || true)
        if [[ -n "$report" ]]; then
            window_pid=$(get_main_window_pid)
            if [[ -n "$window_pid" ]] && printf '%s' "$report" | python3 -c \
                'import json,sys; state=json.load(sys.stdin); assert state.get("process_pid") == int(sys.argv[1]), state; assert state.get("policy") == "server", state; assert state.get("mainContentRendered") is True, state; assert state.get("customTitlebarPresent") is False, state; assert state.get("customControlClusters") == 0, state' \
                "$window_pid"; then
                printf 'Hermes runtime window chrome: server policy, no app titlebar or controls (pid=%s)\n' "$window_pid"
                return 0
            fi
        fi
        sleep 0.2
    done

    echo 'Hermes renderer did not report conforming Shell-owned window chrome' >&2
    "$engine" exec "$name" sh -c \
        'test ! -f /tmp/hermes-window-chrome.json || cat /tmp/hermes-window-chrome.json' >&2 || true
    return 1
}

verify_consumer_restart() {
    "$engine" exec "$name" sh -c 'test "$RESTART_APP" = true'
    old_consumer_pid=$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/consumer.pid)
    old_layoutd_pid=$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/layoutd.pid)
    old_supervisor_pid=$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/layoutd-supervisor.pid)

    if [[ "$kind" == hermes ]]; then
        "$engine" exec "$name" rm -f /tmp/hermes-window-chrome.json
    fi
    "$engine" exec "$name" kill "$old_consumer_pid"

    new_consumer_pid=''
    for _ in $(seq 1 90); do
        candidate=$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/consumer.pid 2>/dev/null || true)
        if [[ -n "$candidate" && "$candidate" != "$old_consumer_pid" ]] \
            && "$engine" exec "$name" kill -0 "$candidate" >/dev/null 2>&1; then
            new_consumer_pid=$candidate
            break
        fi
        sleep 1
    done
    [[ -n "$new_consumer_pid" ]] || {
        echo 'RESTART_APP=true did not relaunch the consumer after it exited' >&2
        return 1
    }

    # Wait for the relaunched app to own the solo Shell window again. The
    # verifier requires healthy layout and bounded geometry convergence.
    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py \
        "$kind" --managed-count 1
    verify_hermes_window_chrome
    sleep 3
    [[ "$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/consumer.pid)" == "$new_consumer_pid" ]]
    [[ "$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/layoutd.pid)" == "$old_layoutd_pid" ]]
    [[ "$("$engine" exec "$name" cat /config/.local/state/pelagian-shell/layoutd-supervisor.pid)" == "$old_supervisor_pid" ]]
    "$engine" exec "$name" kill -0 "$old_layoutd_pid"
    "$engine" exec "$name" kill -0 "$old_supervisor_pid"
}

read -r -a phases <<< "${GROTTO_DESKTOP_PHASES:-store lookup}"
test "${#phases[@]}" -gt 0
restart_qualified=false
for phase in "${phases[@]}"; do
    if [[ "$phase" == lookup ]]; then
        if [[ "$kind" == hermes ]]; then
            "$engine" exec "$name" rm -f /tmp/hermes-window-chrome.json
        fi
        "$engine" restart "$name" >/dev/null
    fi
    CONTAINER_ENGINE="$engine" "$conformance/start-shell-stream.sh" "$name" "$shell_source/tests/selkies-smoke-client.py"
    "$engine" exec "$name" sh -c \
        '! grep -Eiq "<windowRule[^>]*(identifier|app_id|appId|class|title)=|hermes|chatgpt" /config/.config/labwc/rc.xml'
    if [[ "$kind" == chatgpt ]]; then
        window_pid=''
        for _ in $(seq 1 60); do
            window_pid=$(get_main_window_pid || true)
            [[ -z "$window_pid" ]] || break
            sleep 1
        done
        "$engine" exec -i "$name" python3 - "$window_pid" <<'PY'
import pathlib
import sys

consumer_file = pathlib.Path('/config/.local/state/pelagian-shell/consumer.pid')
for label, pid in (('consumer', consumer_file.read_text().strip()),
                   ('window', sys.argv[1])):
    if not pid.isdecimal():
        print(f'{label} process: no PID', flush=True)
        continue
    selected = {}
    for entry in pathlib.Path(f'/proc/{pid}/environ').read_bytes().split(b'\\0'):
        key, sep, value = entry.partition(b'=')
        if sep and key in {b'XDG_RUNTIME_DIR', b'WAYLAND_DISPLAY',
                           b'DISPLAY', b'DBUS_SESSION_BUS_ADDRESS'}:
            selected[key.decode()] = value.decode(errors='replace')
    print(f'{label} process coordinates: {selected}', flush=True)
PY
    fi
    options=(--native)
    if [[ "$kind" == hermes ]]; then options+=(--keyring "$phase"); fi
    if [[ "$kind" == chatgpt ]]; then options+=(--binary-bus-exception); fi
    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py "$kind" "${options[@]}"
    verify_hermes_window_chrome
    if [[ "$restart_qualified" != true ]]; then
        verify_consumer_restart
        restart_qualified=true
    fi
    verify_two_window_dialog_and_reflow
    test "$("$engine" exec "$name" cat /config/consumer-volume-sentinel)" = preserved
    if [[ "$kind" == hermes ]]; then
        "$engine" exec --user abc "$name" /usr/local/libexec/grotto-hermes-desktop-image-smoke
        if "$engine" exec "$name" pgrep -f '[h]ermes serve' >/dev/null; then
            echo 'Desktop unexpectedly started a second Hermes backend' >&2
            exit 1
        fi
    else
        "$engine" exec --user abc "$name" /usr/local/libexec/grotto-chatgpt-desktop-smoke
    fi
done
printf 'grotto-%s-desktop smoke: PASS image=%s engine=%s\n' "$kind" "$image" "$engine"
