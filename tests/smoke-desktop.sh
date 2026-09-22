#!/bin/bash
set -Eeuo pipefail
engine=${CONTAINER_ENGINE:-docker}
kind=${1:?chatgpt or hermes required}
image=${2:?image required}
case "$kind" in chatgpt|hermes) ;; *) exit 64 ;; esac
# Pin the test contract independently from the production Shell image. The
# checked-out tree supplies the viewer, stream driver, and geometry verifier.
shell_revision=a9c6100aabc0cb79deb43910e92639f9b92b4a3d
shell_source=$(mktemp -d)
git -C "$shell_source" init -q
git -C "$shell_source" fetch -q --depth 1 https://github.com/Pelagians/pelagian-shell.git "$shell_revision"
test "$(git -C "$shell_source" rev-parse FETCH_HEAD)" = "$shell_revision"
git -C "$shell_source" checkout -q --detach FETCH_HEAD
conformance="$shell_source/tests/consumer-conformance"
name="grotto-${kind}-desktop-smoke-$$"
volumes=(config workspace tools homebrew cache)
# shellcheck disable=SC2317,SC2329
cleanup() {
    result=$?
    trap - EXIT
    if (( result != 0 )); then
        "$engine" logs "$name" >&2 || true
        # The container shell expands diagnostic paths.
        # shellcheck disable=SC2016
        "$engine" exec "$name" sh -c 'for f in /config/.local/state/pelagian-shell/*.log /config/hermes-desktop/session.log /config/hermes-desktop/hermes-home/logs/desktop.log; do test ! -f "$f" || tail -n 80 "$f"; done' >&2 || true
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
"$engine" run --rm --entrypoint sh --volume "${name}-config:/config" "$image" -c \
    'mkdir -p /config/.codex; printf preserved > /config/consumer-volume-sentinel'
# Exercise the real /init entrypoint. Login uses no real accounts in CI.
"$engine" run -d --name "$name" --shm-size=2g \
    --env "PUID=$(id -u)" --env "PGID=$(id -g)" \
    --env GROTTO_CHATGPT_AUTH_MODE=off \
    --env GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD=ci-ephemeral-keyring \
    --env SELKIES_MANUAL_WIDTH=1920 --env SELKIES_MANUAL_HEIGHT=1080 \
    --volume "${name}-config:/config" --volume "${name}-workspace:/workspace" \
    --volume "${name}-tools:/tools" --volume "${name}-homebrew:/home/linuxbrew/.linuxbrew" \
    --volume "${name}-cache:/cache" "$image" >/dev/null
"$engine" cp "$conformance/verify-shell-session.py" "$name:/tmp/verify-shell-session.py"
for phase in store lookup; do
    if [[ "$phase" == lookup ]]; then
        "$engine" restart "$name" >/dev/null
    fi
    CONTAINER_ENGINE="$engine" "$conformance/start-shell-stream.sh" "$name" "$shell_source/tests/selkies-smoke-client.py"
    options=(--native)
    if [[ "$kind" == hermes ]]; then options+=(--keyring "$phase"); fi
    "$engine" exec --user abc "$name" python3 /tmp/verify-shell-session.py "$kind" "${options[@]}"
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
