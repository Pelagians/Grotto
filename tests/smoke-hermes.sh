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
  # Hermes >=0.22 returns status 1 when doctor identifies missing setup.
  # This disposable smoke environment intentionally has no provider auth or
  # running host gateway. Accept only those two expected findings; any other
  # diagnostic failure must still fail the image qualification.
  report="$(mktemp)"
  status=0
  hermes doctor >"$report" 2>&1 || status=$?
  cat "$report"
  if [ "$status" -ne 0 ]; then
    test "$status" -eq 1
    grep -Fq "Found 2 issue(s) to address:" "$report"
    grep -Fq "No host gateway owns the gateway role" "$report"
    grep -Fq "to configure missing API keys" "$report"
  fi
  rm -f "$report"
'
printf '%s\n' 'grotto Hermes smoke passed'
