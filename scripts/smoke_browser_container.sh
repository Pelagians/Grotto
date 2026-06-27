#!/usr/bin/env bash
# OpenQuad browser-agent container smoke
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${OPENQUAD_BROWSER_IMAGE:-openquad-browser-agent:smoke}"
HOST_PORT="${OPENQUAD_BROWSER_SMOKE_PORT:-18790}"
SKIP_BUILD="${OPENQUAD_SKIP_BUILD:-false}"
WORKSPACE_DIR="${OPENQUAD_SMOKE_WORKSPACE:-}"
CID=""
choose_engine() {
  if [ -n "${CONTAINER_ENGINE:-}" ]; then return 0; fi
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then CONTAINER_ENGINE="podman"
  elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then CONTAINER_ENGINE="sudo podman"
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then CONTAINER_ENGINE="docker"
  else echo "No usable container engine found." >&2; exit 2; fi
}
engine() { ${CONTAINER_ENGINE} "$@"; }
cleanup() {
  if [ -n "${CID}" ]; then engine rm -f "${CID}" >/dev/null 2>&1 || true; fi
  if [ -z "${OPENQUAD_SMOKE_WORKSPACE:-}" ] && [ -n "${WORKSPACE_DIR}" ]; then rm -rf "${WORKSPACE_DIR}"; fi
}
trap cleanup EXIT
choose_engine; cd "${ROOT_DIR}"
if [ "${SKIP_BUILD}" != "true" ]; then
  echo "Building ${IMAGE} with browser-agent template..."
  engine build -f Containerfile --build-arg OPENQUAD_TEMPLATE=browser-agent --build-arg OPENQUAD_IMAGE_NAME=openquad-browser-agent --build-arg "OPENQUAD_VERIFY_TOOLS=" -t "${IMAGE}" "${ROOT_DIR}"
fi
if [ -z "${WORKSPACE_DIR}" ]; then WORKSPACE_DIR="$(mktemp -d -t openquad-browser-smoke.XXXXXX)"; fi
mkdir -p "${WORKSPACE_DIR}/inputs"
echo "Starting ${IMAGE}..."
CID="$(engine run -d --rm -p "127.0.0.1:${HOST_PORT}:18789" -v "${WORKSPACE_DIR}:/home/node/.openclaw/workspace:Z" -e OPENQUAD_WORKSPACE_DIR=/home/node/.openclaw/workspace "${IMAGE}")"
echo "Started ${IMAGE} as ${CID} on 127.0.0.1:${HOST_PORT}"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null
echo "Verifying capabilities..."
CAPS="$(curl -fsS "http://127.0.0.1:${HOST_PORT}/openquad/v1/capabilities")"
echo "${CAPS}" | python3 -c "import json, sys; caps = json.load(sys.stdin); assert 'browser.screenshot' in caps; print('OK')"
TASK_ID="browser-container-smoke"
REQUEST_JSON="${WORKSPACE_DIR}/task-request.json"
RESPONSE_JSON="${WORKSPACE_DIR}/task-response.json"
cat > "${REQUEST_JSON}" <<JSON
{"task_id":"${TASK_ID}","idempotency_key":"smoke:${TASK_ID}","capability":"browser.screenshot","task_type":"screenshot","input":{"url":"https://example.com/"},"constraints":{"max_runtime_seconds":120,"network_policy":"restricted","allowed_domains":["example.com"],"write_scope":"task"},"policy":{"decision":"allowed","reason":"container smoke","policy_version":"v0.1-smoke"},"provenance":{"orchestrator":"container-smoke"}}
JSON
echo "Submitting screenshot task..."
curl -fsS -H 'content-type: application/json' --data-binary "@${REQUEST_JSON}" "http://127.0.0.1:${HOST_PORT}/openquad/v1/tasks" > "${RESPONSE_JSON}"
python3 - "${WORKSPACE_DIR}" "${TASK_ID}" "${RESPONSE_JSON}" <<'PY'
import json, sys; from pathlib import Path
w,tid,rp = Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
r = json.loads(rp.read_text())
assert r["task_id"]==tid and r["capability"]=="browser.screenshot" and r["task_type"]=="screenshot"
assert r["status"]=="failed"
codes=[e["code"] for e in r["errors"]]
assert "browser_endpoint_missing" in codes
assert r["artifacts"]==[]
td=w/"tasks"/tid
for n in ("task.json","result.json","events.jsonl"): assert (td/n).is_file()
ev=[json.loads(l) for l in (td/"events.jsonl").read_text().splitlines()]
ets=[e["event_type"] for e in ev]
assert "task.accepted" in ets and "task.started" in ets and "task.failed" in ets
print(f"CONTAINER_SMOKE_OK task_id={tid} status=failed error_codes={codes}")
PY
