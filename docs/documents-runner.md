# Grotto Documents Runner

`grotto-documents` is the first real Grotto worker runtime. In v0.2.1 it is intentionally narrow: it accepts `documents.convert` tasks with `task_type=convert_pdf_to_text`, reads a PDF from a `file://` URI inside `GROTTO_WORKSPACE_DIR`, and writes deterministic artifacts back into the task workspace.

## Scope

Current scope:

- worker image: `grotto-documents`
- capability: `documents.convert`
- task type: `convert_pdf_to_text`
- source URI scheme: `file://` only
- source boundary: source path must resolve inside `GROTTO_WORKSPACE_DIR`
- outputs:
  - `task.json`
  - `result.json`
  - `events.jsonl`
  - `artifact-manifest.json`
  - `artifacts/output.txt`
  - `artifacts/metadata.json`

Out of scope for this milestone:

- records, communications, browser, or LLM-backed classification workers
- HTTP/S3/source-object fetching
- broad document upload/object storage APIs
- relaxing workspace boundary validation

## Deterministic tools

The documents image is expected to include these tools:

- `pdfinfo`
- `pdftotext`
- `qpdf`
- `tesseract`
- `ocrmypdf`

The extraction order remains deterministic-first:

1. inspect the PDF with `pdfinfo`
2. extract selectable text with `pdftotext`
3. retry after a `qpdf` repair/linearization pass if needed
4. use `ocrmypdf`/`tesseract` fallback for scan-like inputs when available

The runner must fail clearly when required tools or source files are missing. It must not fake success.

## Workspace contract

The worker uses:

```text
GROTTO_WORKSPACE_DIR=/home/node/.openclaw/workspace
```

A valid source URI looks like:

```text
file:///home/node/.openclaw/workspace/inputs/inquiry.pdf
```

The resolved source path must stay inside `GROTTO_WORKSPACE_DIR`. Path traversal, symlink escape, and sources outside the mounted workspace are rejected. This workspace boundary is part of the security contract and should stay strict until Nereus has a proper artifact API or signed object-storage handoff.

Each task writes to:

```text
${GROTTO_WORKSPACE_DIR}/tasks/<task_id>/
```

Artifacts are written under:

```text
${GROTTO_WORKSPACE_DIR}/tasks/<task_id>/artifacts/
```

## Container smoke test

Run the local smoke test from the repository root:

```bash
scripts/smoke_documents_container.sh
```

Useful overrides:

```bash
CONTAINER_ENGINE="sudo podman" \
GROTTO_DOCUMENTS_IMAGE="grotto-documents:smoke" \
GROTTO_SMOKE_PORT=18789 \
scripts/smoke_documents_container.sh
```

The script:

1. builds the documents image from `Containerfile` with `GROTTO_TEMPLATE=documents`
2. verifies `pdfinfo`, `pdftotext`, `qpdf`, `tesseract`, and `ocrmypdf` inside the image
3. starts `grotto-workerd`
4. mounts a temporary workspace at `/home/node/.openclaw/workspace`
5. creates a sample PDF under the workspace
6. submits `documents.convert / convert_pdf_to_text`
7. verifies `output.txt`, `metadata.json`, and `artifact-manifest.json`
8. verifies artifact `sha256` and `size_bytes`

Expected success marker:

```text
CONTAINER_SMOKE_OK task_id=documents-container-smoke ... sha256=<64 hex> size_bytes=<n>
```

## Direct curl example

After the daemon is running on port `18789`:

```bash
curl -fsS http://127.0.0.1:18789/healthz
curl -fsS http://127.0.0.1:18789/grotto/v1/manifest

cat > /tmp/grotto-doc-task.json <<'JSON'
{
  "task_id": "manual-doc-convert-001",
  "idempotency_key": "manual:manual-doc-convert-001",
  "capability": "documents.convert",
  "task_type": "convert_pdf_to_text",
  "input": {
    "source_uri": "file:///home/node/.openclaw/workspace/inputs/inquiry.pdf"
  },
  "constraints": {
    "max_runtime_seconds": 120,
    "network_policy": "none",
    "allowed_domains": [],
    "write_scope": "task"
  },
  "policy": {
    "decision": "allowed",
    "reason": "manual deterministic conversion",
    "policy_version": "v0.2.1"
  },
  "provenance": {
    "orchestrator": "manual-curl"
  }
}
JSON

curl -fsS \
  -H 'content-type: application/json' \
  --data-binary @/tmp/grotto-doc-task.json \
  http://127.0.0.1:18789/grotto/v1/tasks
```

The response contains artifact metadata and the workspace contains the durable files listed above.
