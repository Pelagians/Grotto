#!/usr/bin/env bash
# Opt-in MCP image smoke. No tenant credentials or provider data required.
set -Eeuo pipefail
image="${GROTTO_HERMES_IMAGE:-localhost/grotto-hermes:dev}"
engine="${CONTAINER_ENGINE:-podman}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="$root/runtimes/hermes/nereus-mcp.example.yaml"
security_args=()
if [[ "$engine" == *podman* ]]; then
  security_args=(--security-opt label=disable)
fi

"$engine" run --rm --entrypoint test "$image" -f /usr/local/libexec/pelagian-nereus-mcp.py
disabled="$("$engine" run --rm --entrypoint /opt/hermes/.venv/bin/hermes "$image" mcp list)"
if [[ "$disabled" == *pelagian_nereus* ]]; then
  echo "Pelagian MCP must be absent from default Hermes configuration" >&2
  exit 1
fi

enabled="$("$engine" run --rm "${security_args[@]}" \
  -v "$config:/opt/data/config.yaml:ro" \
  --entrypoint /opt/hermes/.venv/bin/hermes "$image" mcp list)"
if [[ "$enabled" != *pelagian_nereus* || "$enabled" != *enabled* ]]; then
  echo "Hermes did not recognize the opt-in Pelagian MCP server" >&2
  exit 1
fi

tool_summary="$("$engine" run --rm -t "${security_args[@]}" \
  -v "$config:/opt/data/config.yaml:ro" \
  --entrypoint /opt/hermes/.venv/bin/hermes "$image" tools --summary)"
if [[ "$tool_summary" != *pelagian_nereus* ||
      "$tool_summary" == *terminal* || "$tool_summary" == *"File Operations"* ]]; then
  echo "Synthetic Hermes profile exposed an unexpected built-in tool" >&2
  exit 1
fi

doctor="$("$engine" run --rm "${security_args[@]}" \
  -v "$config:/opt/data/config.yaml:ro" \
  --entrypoint /opt/hermes/.venv/bin/hermes "$image" doctor)"
if [[ "$doctor" != *"No suspicious MCP stdio commands"* ]]; then
  echo "Hermes doctor did not accept the Pelagian MCP command" >&2
  exit 1
fi
echo "Hermes Nereus MCP image smoke passed"
