#!/bin/bash
set -Eeuo pipefail

export HOME="${HOME:-/config}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/config/.claude}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/config/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/config/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-/config/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-/config/.local/state}"

expected_fingerprint=31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE
keyring=/usr/share/keyrings/claude-desktop-archive-keyring.asc
repository=/etc/apt/sources.list.d/claude-desktop.list
version_file=/usr/share/grotto/claude-desktop-version
architecture="$(dpkg --print-architecture)"

case "$architecture" in
    amd64|arm64) ;;
    *) echo "Unsupported architecture: $architecture" >&2; exit 1 ;;
esac

command -v claude-desktop >/dev/null
command -v gnome-keyring-daemon >/dev/null
command -v selkies >/dev/null
test -x /usr/bin/claude-desktop
test -x /lsiopy/bin/selkies
test -r "$keyring"
test -r "$repository"
test -s "$version_file"

gpg --batch --show-keys --with-colons "$keyring" \
    | awk -F: '$1 == "fpr" { print $10; exit }' \
    | grep -Fx "$expected_fingerprint"

grep -Fx \
    "deb [arch=${architecture} signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main" \
    "$repository"

installed_version="$(dpkg-query -W -f='${Version}' claude-desktop)"
test -n "$installed_version"
test "$(cat "$version_file")" = "$installed_version"

for directory in \
    /config \
    "$CLAUDE_CONFIG_DIR" \
    "$XDG_CONFIG_HOME" \
    "$XDG_CACHE_HOME" \
    "$XDG_DATA_HOME" \
    "$XDG_STATE_HOME" \
    /workspace \
    /tools \
    /cache
do
    test -d "$directory"
    test -w "$directory"
    probe="$directory/.grotto-claude-smoke-$$"
    : > "$probe"
    rm -f "$probe"
done

test "$(stat -c '%a' "$CLAUDE_CONFIG_DIR")" = 700
test "$(stat -c '%a' "$XDG_DATA_HOME/keyrings")" = 700

printf 'Claude Desktop %s runtime smoke test passed\n' "$installed_version"
