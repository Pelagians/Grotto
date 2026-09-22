#!/bin/bash
# shellcheck disable=SC2251 # `! grep` assertions intentionally fail the smoke.
set -Eeuo pipefail
trap 'printf "runtime smoke failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

if [[ "$(id -un)" != "abc" ]]; then
    echo "runtime smoke test must run as abc" >&2
    exit 1
fi

required=(
    bash
    bwrap
    chatgpt
    codex
    curl
    find
    gh
    git
    jq
    lsof
    node
    npm
    pip3
    pelagian-layoutd
    pelagian-shellctl
    pkg-config
    python3
    rg
    shellcheck
    sqlite3
    unzip
    wlrctl
    zip
)
for command_name in "${required[@]}"; do
    if ! command -v "$command_name" >/dev/null; then
        echo "required command not found on PATH: $command_name" >&2
        exit 1
    fi
done

test ! -e /usr/local/libexec/grotto-configure-openbox
test -x /usr/local/bin/grotto-chatgpt-desktop
test ! -e /usr/local/libexec/grotto-chatgpt-fullscreen
test -x /defaults/autostart
test -x /usr/local/bin/pelagian-shell-consumer
test -x /defaults/autostart_wayland
grep -q 'consumer_hook=/usr/local/bin/pelagian-shell-consumer' /defaults/autostart_wayland
test -f /defaults/labwc.xml

# The live window may still be reconciling immediately after the viewer and
# native-window check. Require healthy status within a bounded interval.
shell_status=''
shell_healthy=false
for _ in $(seq 1 15); do
    shell_status="$(pelagian-shellctl status)"
    if jq -e '
      .compositor_adapter == "labwc-ipc" and
      .runtime.layoutd == "healthy" and
      .runtime.adapter_connected == true and
      .runtime.reconciliation == "healthy"
    ' <<<"$shell_status" >/dev/null; then
        shell_healthy=true
        break
    fi
    sleep 1
done
if [[ "$shell_healthy" != true ]]; then
    printf 'Shell did not settle to healthy status: %s\n' "$shell_status" >&2
    exit 1
fi
pelagian-shellctl config show >/dev/null
layoutd_status="$(pelagian-layoutd status)"
if grep -q planner_only <<<"$layoutd_status"; then
    echo "pelagian-layoutd is still planner-only" >&2
    exit 1
fi
jq -e '.compositor_adapter == "labwc-ipc"' <<<"$layoutd_status" >/dev/null

# Shell owns Labwc placement; the consumer carries no product-specific sizing.
test "$(printenv PIXELFLUX_WAYLAND)" = true
! grep -q 'identifier="chatgpt-desktop"' /defaults/labwc.xml
! grep -q 'exec /defaults/autostart' /usr/local/bin/pelagian-shell-consumer

# The vendor package supplies the application, the Codex CLI, and the Node
# runtime as one unit. Check the entry points Grotto actually launches rather
# than only that the commands resolve on PATH.
test -x /usr/lib/chatgpt/ChatGPT
test -x /usr/lib/chatgpt/resources/codex
test -x /usr/lib/chatgpt/resources/cua_node/bin/node
test "$(command -v node)" = /usr/lib/chatgpt/resources/cua_node/bin/node

# The pinned build must not have left an auto-update source behind.
test ! -e /etc/apt/sources.list.d/chatgpt.sources

# The session launcher creates these as the desktop user before starting the
# app. A root-owned copy left by the build or by older persistent state makes
# that fail, which stops the desktop from coming up at all.
for path in /config/.cache /config/.config /config/.local/state; do
    if ! install -d -m 0755 "$path"; then
        echo "session launcher cannot prepare: $path" >&2
        ls -ld "$path" >&2 || true
        exit 1
    fi
done

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
  .schema_version == 2 and
  .source == "installed-vendor-package" and
  .package.name == "chatgpt" and
  .node_repl.verified == true and
  .node_repl.auto_approved == false and
  .node_repl.verification_source == "installed-vendor-package" and
  .browser_use.verified == true
' "$security_manifest" >/dev/null

# The recorded policy must describe the package that is actually installed.
installed_version="$(dpkg-query --show --showformat='${Version}' chatgpt)"
# shellcheck disable=SC2016
jq -e --arg version "$installed_version" '.package.version == $version' \
    "$security_manifest" >/dev/null

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
  .browser_use_present == $policy.browser_use.present and
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
  chatgpt_package: .runtime.chatgpt_package_version,
  active_probe: .active_probe,
  sandbox_probe: .sandbox_probe.status,
  selected_backend: .sandbox.selected_backend,
  backend_working: .sandbox.backend_working,
  node_repl_exposed: .node_repl_exposed,
  node_repl_verified: .node_repl_verified,
  browser_use_policy_verified: .browser_use_policy_verified,
  cached_probe_available: (.cached_sandbox_probe.result != null)
}' "$report"
