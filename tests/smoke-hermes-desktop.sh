#!/bin/bash
set -Eeuo pipefail

engine=${CONTAINER_ENGINE:-docker}
image=${GROTTO_HERMES_DESKTOP_IMAGE:-grotto-hermes-desktop:dev}
name="grotto-hermes-desktop-smoke-$$"
port=${GROTTO_HERMES_DESKTOP_SMOKE_PORT:-13002}
volumes=(config workspace tools homebrew cache)

# Invoked indirectly by the trap below; ShellCheck versions classify this as
# unreachable or unreferenced depending on their control-flow implementation.
# shellcheck disable=SC2317,SC2329
cleanup() {
    "$engine" rm -f "$name" >/dev/null 2>&1 || true
    for volume in "${volumes[@]}"; do
        "$engine" volume rm -f "${name}-${volume}" >/dev/null 2>&1 || true
    done
}
trap cleanup EXIT INT TERM

for volume in "${volumes[@]}"; do
    "$engine" volume create "${name}-${volume}" >/dev/null
done

"$engine" run -d \
    --name "$name" \
    --shm-size=2g \
    --publish "127.0.0.1:${port}:3001" \
    --env "PUID=$(id -u)" \
    --env "PGID=$(id -g)" \
    --env PIXELFLUX_WAYLAND=true \
    --env GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD=ci-ephemeral-keyring \
    --volume "${name}-config:/config" \
    --volume "${name}-workspace:/workspace" \
    --volume "${name}-tools:/tools" \
    --volume "${name}-homebrew:/home/linuxbrew/.linuxbrew" \
    --volume "${name}-cache:/cache" \
    "$image" >/dev/null

for _ in $(seq 1 180); do
    if "$engine" exec "$name" pgrep -x labwc >/dev/null 2>&1 \
        && "$engine" exec "$name" pgrep -f '[H]ermes' >/dev/null 2>&1 \
        && "$engine" exec "$name" pgrep -f '[g]nome-keyring-daemon' >/dev/null 2>&1 \
        && curl --fail --silent --show-error --insecure --max-time 3 \
            "https://127.0.0.1:${port}/" >/dev/null 2>&1; then
        "$engine" exec "$name" /usr/local/libexec/grotto-hermes-desktop-image-smoke
        inventory="$($engine exec "$name" /usr/bin/with-contenv \
            s6-setuidgid abc wlrctl toplevel list)"
        printf 'Hermes Desktop window inventory:\n%s\n' "$inventory"
        if ! grep -qi hermes <<< "$inventory"; then
            echo "Hermes Desktop did not expose an observable toplevel" >&2
            exit 1
        fi
        if "$engine" exec "$name" pgrep -f '[h]ermes serve' >/dev/null 2>&1; then
            echo "Desktop unexpectedly started a second Hermes backend" >&2
            exit 1
        fi
        echo "grotto-hermes-desktop smoke: PASS image=$image engine=$engine"
        exit 0
    fi
    sleep 1
done

"$engine" logs "$name" >&2 || true
"$engine" exec "$name" cat /config/hermes-desktop/session.log >&2 || true
"$engine" exec "$name" ps aux >&2 || true
echo "grotto-hermes-desktop smoke: startup did not become ready" >&2
exit 1
