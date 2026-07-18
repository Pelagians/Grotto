#!/bin/bash
set -Eeuo pipefail

export HOME="${HOME:-/config}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/config/.claude}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/config/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/config/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-/config/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-/config/.local/state}"
export GROTTO_CLAUDE_VIEWER_EVENT_FILE="${GROTTO_CLAUDE_VIEWER_EVENT_FILE:-/usr/share/selkies/web/grotto-claude-open-url.json}"
export BROWSER="${BROWSER:-/usr/local/bin/grotto-claude-browser}"

expected_fingerprint=31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE
keyring=/usr/share/keyrings/claude-desktop-archive-keyring.asc
repository=/etc/apt/sources.list.d/claude-desktop.list
version_file=/usr/share/grotto/claude-desktop-version
viewer_script=/usr/share/grotto/claude-viewer-open.js
architecture="$(dpkg --print-architecture)"
gnupg_home="$(mktemp -d)"
chmod 0700 "$gnupg_home"
trap 'rm -rf "$gnupg_home"' EXIT

case "$architecture" in
    amd64|arm64) ;;
    *) echo "Unsupported architecture: $architecture" >&2; exit 1 ;;
esac

for command_name in \
    claude-desktop gnome-keyring-daemon python3 selkies xdg-mime
do
    command -v "$command_name" >/dev/null
done

test -x /usr/bin/claude-desktop
test -x /usr/local/bin/grotto-claude-browser
test -x /lsiopy/bin/selkies
test -r /usr/share/applications/grotto-claude-browser.desktop
test -r "$viewer_script"
test -r "$keyring"
test -r "$repository"
test -s "$version_file"

python3 /usr/local/bin/grotto-claude-browser --self-test

grep -Fq 'target="_blank"' "$viewer_script"
grep -Fq 'parsed.protocol !== "https:"' "$viewer_script"
grep -Fq 'credentials: "same-origin"' "$viewer_script"
if grep -Fq 'host.sock' /usr/local/bin/grotto-claude-browser; then
    echo "Claude browser handler still depends on a host socket" >&2
    exit 1
fi

gpg --batch --homedir "$gnupg_home" --show-keys --with-colons "$keyring" \
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

xdg-mime default grotto-claude-browser.desktop text/html
xdg-mime default grotto-claude-browser.desktop x-scheme-handler/http
xdg-mime default grotto-claude-browser.desktop x-scheme-handler/https

test "$(xdg-mime query default text/html)" = grotto-claude-browser.desktop
test "$(xdg-mime query default x-scheme-handler/http)" = grotto-claude-browser.desktop
test "$(xdg-mime query default x-scheme-handler/https)" = grotto-claude-browser.desktop

dashboard_count=0
for dashboard in /usr/share/selkies/selkies-dashboard*; do
    [[ -d "$dashboard" ]] || continue
    index="$dashboard/index.html"
    script="$dashboard/grotto-claude-viewer-open.js"
    event="$dashboard/grotto-claude-open-url.json"

    test -r "$index"
    test -r "$script"
    test -w "$event"
    test "$(stat -c '%a' "$event")" = 644
    grep -Fq 'grotto-claude-viewer-open.js' "$index"

    python3 - "$event" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload == {"version": 1, "id": "", "created_at": 0, "url": ""}
PY

    dashboard_count=$((dashboard_count + 1))
done
test "$dashboard_count" -gt 0

test "$(stat -c '%a' "$CLAUDE_CONFIG_DIR")" = 700
test "$(stat -c '%a' "$XDG_DATA_HOME/keyrings")" = 700

printf 'Claude Desktop %s runtime smoke test passed\n' "$installed_version"
