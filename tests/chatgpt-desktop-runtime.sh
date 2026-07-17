#!/bin/bash
set -Eeuo pipefail

if [[ "$(id -un)" != "abc" ]]; then
    echo "runtime smoke test must run as abc" >&2
    exit 1
fi

required=(
    bash
    curl
    find
    gh
    git
    jq
    lsof
    node
    npm
    pip3
    pkg-config
    python3
    rg
    shellcheck
    sqlite3
    unzip
    zip
)
for command_name in "${required[@]}"; do
    if ! command -v "$command_name" >/dev/null; then
        echo "required command not found on PATH: $command_name" >&2
        exit 1
    fi
done

bundled_bwrap="$(find /opt/codex-cli/lib/node_modules/@openai/codex \
    -path '*/codex-resources/bwrap' -type f -perm /111 -print -quit)"
test -n "$bundled_bwrap"
test -x "$bundled_bwrap"

/bin/true

for path in /config /workspace /tools /cache; do
    if [[ ! -d "$path" || ! -w "$path" ]]; then
        echo "required writable directory is unavailable: $path" >&2
        ls -ld "$path" >&2 || true
        exit 1
    fi
done

report="$(mktemp)"
trap 'rm -f "$report"' EXIT

doctor_rc=0
grotto-doctor --json > "$report" || doctor_rc=$?

jq -e '.schema_version == 1' "$report" >/dev/null
jq -e '.identity.user == "abc"' "$report" >/dev/null
jq -e '.checks.direct_command.ok == true' "$report" >/dev/null
jq -e '.checks | has("bubblewrap_fresh_dev")' "$report" >/dev/null
jq -e '.checks | has("bubblewrap_protected_child_remount")' "$report" >/dev/null
jq -e '.checks | has("codex_workspace_permissions")' "$report" >/dev/null
jq -e '.checks | has("landlock_read_only")' "$report" >/dev/null
jq -e '.security.selinux | has("host_audit_access") and has("attribution")' \
    "$report" >/dev/null
jq -e '.sandbox.automatic_fallback_enabled == false' "$report" >/dev/null
jq -e '.paths["/config"].writable == true' "$report" >/dev/null
jq -e '.paths["/workspace"].writable == true' "$report" >/dev/null
jq -e '.paths["/tools"].writable == true' "$report" >/dev/null
jq -e '.paths["/cache"].writable == true' "$report" >/dev/null

case "${GROTTO_EXPECT_CODEX_SANDBOX:-record}" in
    pass)
        jq -e '.checks.codex_workspace_permissions.ok == true' "$report" >/dev/null
        test "$doctor_rc" -eq 0
        ;;
    fail)
        jq -e '.checks.codex_workspace_permissions.ok == false' "$report" >/dev/null
        test "$doctor_rc" -ne 0
        ;;
    record)
        ;;
    *)
        echo "invalid GROTTO_EXPECT_CODEX_SANDBOX value" >&2
        exit 64
        ;;
esac

jq -c '{
  doctor_ok: .ok,
  selected_backend: .sandbox.selected_backend,
  direct: .checks.direct_command.ok,
  bubblewrap: .checks.bubblewrap_fresh_dev.ok,
  protected_remount: .checks.bubblewrap_protected_child_remount.ok,
  codex_workspace: .checks.codex_workspace_permissions.ok,
  landlock_read_only: .checks.landlock_read_only.ok
}' "$report"
