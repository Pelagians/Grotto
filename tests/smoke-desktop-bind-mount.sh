#!/bin/bash
set -Eeuo pipefail

kind=${1:?chatgpt or hermes required}
image=${2:?image required}
test "$kind" = chatgpt || test "$kind" = hermes
if [[ "$(podman info --format '{{.Host.Security.Rootless}}')" != true ]]; then
    echo 'Grotto bind-mount smoke requires rootless Podman' >&2
    exit 2
fi

host_config=$(mktemp -d)
trap 'rm -rf "$host_config"' EXIT
mkdir -p "$host_config/.XDG" "$host_config/.local/share/keyrings"
printf '%s\n' obsolete-runtime-state > "$host_config/.XDG/legacy-sentinel"

CONTAINER_ENGINE=podman \
GROTTO_CONFIG_BIND="$host_config" \
GROTTO_DESKTOP_PHASES=store \
tests/smoke-desktop.sh "$kind" "$image"

test ! -e "$host_config/.XDG/legacy-sentinel"
test "$(cat "$host_config/consumer-volume-sentinel")" = preserved

CONTAINER_ENGINE=podman \
GROTTO_CONFIG_BIND="$host_config" \
GROTTO_DESKTOP_PHASES=lookup \
GROTTO_EXPECT_CONFIG_PERSISTENCE=true \
tests/smoke-desktop.sh "$kind" "$image"

test ! -e "$host_config/.XDG/legacy-sentinel"
test "$(cat "$host_config/consumer-volume-sentinel")" = preserved
printf 'grotto-%s bind-mount smoke: PASS image=%s rootless-podman\n' "$kind" "$image"
