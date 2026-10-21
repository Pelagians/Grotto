#!/usr/bin/env bash
# The single-quoted payloads are intentionally evaluated inside the container.
# shellcheck disable=SC2016
set -Eeuo pipefail
image="${GROTTO_HERMES_IMAGE:-grotto-hermes:dev}"
engine="${CONTAINER_ENGINE:-docker}"
run_name="grotto-hermes-smoke-$RANDOM"
tmp="$(mktemp -d)"
cleanup() {
  "$engine" rm -f "$run_name" "$run_name-recreated" >/dev/null 2>&1 || true
  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo rm -rf "$tmp"
  else
    rm -rf "$tmp"
  fi
}
trap cleanup EXIT
mkdir -p "$tmp"/{data,workspace,tools,brew,cache}

common=(-v "$tmp/data:/opt/data" -v "$tmp/workspace:/workspace" -v "$tmp/tools:/tools" -v "$tmp/brew:/home/linuxbrew/.linuxbrew" -v "$tmp/cache:/cache")
"$engine" run --name "$run_name" "${common[@]}" "$image" sh -ceu '
  test "$(id -u)" = 10000
  test "$(hermes --version >/dev/null 2>&1; echo $?)" = 0
  test ! -w /opt/hermes
  test -w /opt/data && test -w /workspace
  command -v brew && brew --version
  command -v jq && command -v yq && command -v rg && command -v uv && command -v mise
  brew install hello
  test -x "$(brew --prefix hello)/bin/hello"
  test -x /opt/hermes/.venv/bin/hermes
  ! pgrep -x supervisord >/dev/null
  ! pgrep -f '[h]ermes-webui' >/dev/null
'
"$engine" run --name "$run_name-recreated" "${common[@]}" "$image" sh -ceu '
  test -x "$(brew --prefix hello)/bin/hello"
  test "$(brew --prefix hello)" != ""
  # A disposable smoke image deliberately lacks API credentials and a running
  # gateway. Hermes doctor exits 1 for those setup findings. Its npm audit
  # also queries a changing advisory database: new upstream noncritical
  # workspace vulnerabilities must be reported, not misread as image failure.
  report="$(mktemp)"
  status=0
  hermes doctor >"$report" 2>&1 || status=$?
  cat "$report"
  test "$status" -eq 0 || test "$status" -eq 1

  # Keep important, stable runtime and security checks mandatory.
  grep -Fq "No suspicious MCP stdio commands" "$report"
  grep -Fq "Runtime venv staged" "$report"
  grep -Fq "Dashboard web surface (imports cleanly)" "$report"
  if grep -Eq "workspace deps \\([1-9][0-9]* critical" "$report"; then
    echo "Critical upstream npm audit findings in Hermes image" >&2
    exit 1
  fi

  # Do not broadly ignore doctor failures. Only the expected lack of
  # configuration and noncritical npm workspace advisories may be present.
  if [ "$status" -ne 0 ]; then
    grep -Eq "^  Found [0-9]+ issue\\(s\\) to address:" "$report"
    grep -E "^  [0-9]+[.] " "$report" | while IFS= read -r finding; do
      case "$finding" in
        *"No host gateway owns the gateway role"*|*"configure missing API keys"*|*"web workspace has "*"npm vulnerabilities"*|*"ui-tui workspace has "*"npm vulnerabilities"*)
          ;;
        *)
          echo "Unexpected Hermes doctor issue: $finding" >&2
          exit 1
          ;;
      esac
    done
  fi
  rm -f "$report"
'
printf '%s\n' 'grotto Hermes smoke passed'
