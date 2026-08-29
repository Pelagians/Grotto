#!/usr/bin/env bash
# The single-quoted payloads are intentionally evaluated inside the container.
# shellcheck disable=SC2016
set -Eeuo pipefail
image="${GROTTO_HERMES_IMAGE:-grotto-hermes:dev}"
engine="${CONTAINER_ENGINE:-docker}"
run_name="grotto-hermes-smoke-$RANDOM"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"; "$engine" rm -f "$run_name" "$run_name-recreated" >/dev/null 2>&1 || true' EXIT
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
  hermes doctor
'
printf '%s\n' 'grotto Hermes smoke passed'
