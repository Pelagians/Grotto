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

test -x /usr/local/libexec/grotto-configure-openbox
test -x /defaults/autostart
test -x /defaults/autostart_wayland
test -f /defaults/labwc.xml

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

security_manifest=/usr/share/grotto/chatgpt-desktop-security.json
test -r "$security_manifest"
test "$(stat -c '%a' "$security_manifest")" = 444
jq -e '
  .schema_version == 1 and
  (.wrapper_revision | test("^[0-9a-f]{40}$")) and
  .node_repl.verified == true and
  .node_repl.auto_approved == false and
  .node_repl.verification_source == "installed-electron-bundle" and
  .browser_use.verified == true
' "$security_manifest" >/dev/null

report="$(mktemp)"
trap 'rm -f "$report"' EXIT

doctor_rc=0
grotto-doctor --json > "$report" || doctor_rc=$?

jq -e '.schema_version == 1' "$report" >/dev/null
jq -e '.identity.user == "abc"' "$report" >/dev/null
jq -e '.ok == null' "$report" >/dev/null
jq -e '.active_probe == false' "$report" >/dev/null
# $security and $policy below are jq variables, not shell variables.
# shellcheck disable=SC2016
jq --slurpfile security "$security_manifest" -e '
  $security[0] as $policy |
  .node_repl_exposed == $policy.node_repl.exposed and
  .node_repl_auto_approved == $policy.node_repl.auto_approved and
  .node_repl_verified == $policy.node_repl.verified and
  .node_repl_policy_source == $policy.node_repl.verification_source and
  .browser_use_trusted_client_hash_patch ==
    $policy.browser_use.trusted_client_hash_patch and
  .browser_use_policy_verified == $policy.browser_use.verified and
  .chatgpt_desktop_security.manifest_error == null
' "$report" >/dev/null
jq -e '.may_generate_host_avcs == false' "$report" >/dev/null
jq -e '.probe_started_at == null and .probe_completed_at == null' "$report" >/dev/null
jq -e '.sandbox_probe.status == "not_run"' "$report" >/dev/null
jq -e '.sandbox_probe.reason == "active probe requires --probe-sandbox"' "$report" >/dev/null
jq -e '.checks == {}' "$report" >/dev/null
jq -e '.security.selinux | has("host_audit_access") and has("attribution")' \
    "$report" >/dev/null
jq -e '.sandbox.automatic_fallback_enabled == false' "$report" >/dev/null
jq -e '.sandbox.backend_working == null' "$report" >/dev/null
jq -e '.sandbox.known_fedora_compatibility.status == "known_incompatible"' \
    "$report" >/dev/null
jq -e '.paths["/config"].writable == true' "$report" >/dev/null
jq -e '.paths["/workspace"].writable == true' "$report" >/dev/null
jq -e '.paths["/tools"].writable == true' "$report" >/dev/null
jq -e '.paths["/cache"].writable == true' "$report" >/dev/null

test "$doctor_rc" -eq 0

jq -c '{
  doctor_ok: .ok,
  active_probe: .active_probe,
  sandbox_probe: .sandbox_probe.status,
  selected_backend: .sandbox.selected_backend,
  backend_working: .sandbox.backend_working,
  node_repl_exposed: .node_repl_exposed,
  node_repl_verified: .node_repl_verified,
  browser_use_policy_verified: .browser_use_policy_verified,
  cached_probe_available: (.cached_sandbox_probe.result != null)
}' "$report"
