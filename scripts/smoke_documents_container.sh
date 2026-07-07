#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${GROTTO_DOCUMENTS_IMAGE:-grotto-documents:smoke}"
HOST_PORT="${GROTTO_SMOKE_PORT:-18789}"
SKIP_BUILD="${GROTTO_SKIP_BUILD:-false}"
WORKSPACE_DIR="${GROTTO_SMOKE_WORKSPACE:-}"
CID=""

choose_engine() {
  if [ -n "${CONTAINER_ENGINE:-}" ]; then
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    CONTAINER_ENGINE="podman"
  elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then
    CONTAINER_ENGINE="sudo podman"
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    CONTAINER_ENGINE="docker"
  else
    echo "No usable container engine found. Tried rootless podman, sudo podman, and docker." >&2
    echo "If Docker is available, start the daemon or set CONTAINER_ENGINE explicitly." >&2
    exit 2
  fi
}

engine() {
  # CONTAINER_ENGINE may intentionally contain two words, e.g. "sudo podman".
  # shellcheck disable=SC2086
  ${CONTAINER_ENGINE} "$@"
}

cleanup() {
  if [ -n "${CID}" ]; then
    engine rm -f "${CID}" >/dev/null 2>&1 || true
  fi
  if [ -z "${GROTTO_SMOKE_WORKSPACE:-}" ] && [ -n "${WORKSPACE_DIR}" ]; then
    rm -rf "${WORKSPACE_DIR}"
  fi
}
trap cleanup EXIT

choose_engine
cd "${ROOT_DIR}"

if [ "${SKIP_BUILD}" != "true" ]; then
  echo "Building ${IMAGE} with documents template..."
  engine build \
    -f Containerfile \
    --build-arg GROTTO_TEMPLATE=documents \
    --build-arg GROTTO_IMAGE_NAME=grotto-documents \
    --build-arg "GROTTO_VERIFY_TOOLS=pdfinfo pdftotext qpdf tesseract ocrmypdf" \
    -t "${IMAGE}" \
    "${ROOT_DIR}"
fi

if [ -z "${WORKSPACE_DIR}" ]; then
  WORKSPACE_DIR="$(mktemp -d -t grotto-documents-smoke.XXXXXX)"
fi
mkdir -p "${WORKSPACE_DIR}/inputs"

python3 - "${WORKSPACE_DIR}/inputs/sample.pdf" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
page_stream = (
    "BT\n"
    "/F1 12 Tf\n"
    "50 750 Td\n"
    "(Hello from Grotto container smoke.) Tj\n"
    "0 -20 Td\n"
    "(convert_pdf_to_text should extract this line.) Tj\n"
    "ET"
)
stream_bytes = page_stream.encode("latin-1")
pdf = b"%PDF-1.4\n"
offsets = []
offsets.append(len(pdf)); pdf += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
offsets.append(len(pdf)); pdf += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
offsets.append(len(pdf)); pdf += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
offsets.append(len(pdf)); pdf += f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode(); pdf += stream_bytes; pdf += b"\nendstream\nendobj\n"
offsets.append(len(pdf)); pdf += b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n"
xref_offset = len(pdf)
pdf += b"xref\n" + f"0 {len(offsets) + 1}\n".encode() + b"0000000000 65535 f \n"
for off in offsets:
    pdf += f"{off:010d} 00000 n \n".encode()
pdf += b"trailer\n" + f"<< /Size {len(offsets) + 1} /Root 1 0 R >>\n".encode() + b"startxref\n" + f"{xref_offset}\n".encode() + b"%%EOF\n"
path.write_bytes(pdf)
PY

CID="$(engine run -d --rm \
  -p "127.0.0.1:${HOST_PORT}:18789" \
  -v "${WORKSPACE_DIR}:/home/node/.openclaw/workspace:Z" \
  -e GROTTO_WORKSPACE_DIR=/home/node/.openclaw/workspace \
  "${IMAGE}")"

echo "Started ${IMAGE} as ${CID} on 127.0.0.1:${HOST_PORT}"

for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null

echo "Verifying deterministic document tools in container..."
engine exec "${CID}" sh -lc 'set -e; for tool in pdfinfo pdftotext qpdf tesseract ocrmypdf; do command -v "$tool"; done'

TASK_ID="documents-container-smoke"
REQUEST_JSON="${WORKSPACE_DIR}/task-request.json"
RESPONSE_JSON="${WORKSPACE_DIR}/task-response.json"
cat > "${REQUEST_JSON}" <<JSON
{
  "task_id": "${TASK_ID}",
  "idempotency_key": "smoke:${TASK_ID}",
  "capability": "documents.convert",
  "task_type": "convert_pdf_to_text",
  "input": {
    "source_uri": "file:///home/node/.openclaw/workspace/inputs/sample.pdf"
  },
  "constraints": {
    "max_runtime_seconds": 120,
    "network_policy": "none",
    "allowed_domains": [],
    "write_scope": "task"
  },
  "policy": {
    "decision": "allowed",
    "reason": "container smoke",
    "policy_version": "v0.2.1-smoke"
  },
  "provenance": {
    "orchestrator": "container-smoke"
  }
}
JSON

curl -fsS \
  -H 'content-type: application/json' \
  --data-binary "@${REQUEST_JSON}" \
  "http://127.0.0.1:${HOST_PORT}/grotto/v1/tasks" \
  > "${RESPONSE_JSON}"

python3 - "${WORKSPACE_DIR}" "${TASK_ID}" "${RESPONSE_JSON}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
workspace = Path(sys.argv[1])
task_id = sys.argv[2]
response_path = Path(sys.argv[3])
task_dir = workspace / "tasks" / task_id
artifacts_dir = task_dir / "artifacts"
response = json.loads(response_path.read_text())
assert response["status"] == "succeeded", response
output = artifacts_dir / "output.txt"
metadata = artifacts_dir / "metadata.json"
manifest_path = task_dir / "artifact-manifest.json"
result_path = task_dir / "result.json"
for path in (output, metadata, manifest_path, result_path):
    assert path.is_file(), f"missing {path}"
text = output.read_text(encoding="utf-8", errors="replace")
assert "Grotto container smoke" in text
manifest = json.loads(manifest_path.read_text())
result = json.loads(result_path.read_text())
assert manifest["task_id"] == task_id
assert result["task_id"] == task_id
by_kind = {item["kind"]: item for item in manifest["artifacts"]}
assert "text" in by_kind, manifest
assert "json" in by_kind, manifest
for kind, path in (("text", output), ("json", metadata)):
    entry = by_kind[kind]
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    size_bytes = path.stat().st_size
    assert entry["sha256"] == sha256, (kind, entry["sha256"], sha256)
    assert entry["size_bytes"] == size_bytes, (kind, entry["size_bytes"], size_bytes)
meta = json.loads(metadata.read_text())
assert meta["text_artifact_sha256"] == by_kind["text"]["sha256"]
assert meta["text_artifact_size_bytes"] == by_kind["text"]["size_bytes"]
print(f"CONTAINER_SMOKE_OK task_id={task_id} output.txt={output} metadata.json={metadata} artifact-manifest.json={manifest_path} sha256={by_kind['text']['sha256']} size_bytes={by_kind['text']['size_bytes']}")
PY
