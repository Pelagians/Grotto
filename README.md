# OpenQuad

OpenQuad is the product/family name for a four-agent starter bundle of minimal OpenClaw container templates plus split browser runtimes. The design goal is the opposite of a large do-everything Hermes context: each OpenQuad agent should be small, connected to a small local model when possible, and equipped with only the tools needed for one constrained job.

OpenQuad agents are narrow workers, not mini-Hermes instances. All writes should be auditable. Autonomous writes are allowed only when bounded by policy. Destructive, financial, security-sensitive, external-communication, or irreversible actions require confirmation or are blocked by default.

## Image Matrix

| Image | Kind | Purpose |
| --- | --- | --- |
| `ghcr.io/myos-dev/openquad-comms:latest` | OpenClaw agent | Email, messaging, calendar, reminders, contacts, scheduling, follow-up |
| `ghcr.io/myos-dev/openquad-records:latest` | OpenClaw agent | Structured business records with VIC/Postgres/SQLite/JSON/CSV support |
| `ghcr.io/myos-dev/openquad-documents:latest` | OpenClaw agent | Read, classify, OCR, extract, convert, draft, and organize documents |
| `ghcr.io/myos-dev/openquad-browser-agent:latest` | OpenClaw agent | Browser workflows through separate browser runtime containers |

See [`docs/image-matrix.md`](docs/image-matrix.md) for the detailed data surfaces, permissions, allowed tools, out-of-scope actions, and output contracts.

## Template Layout

```text
templates/
  communications-calendar/
    Brewfile
    openclaw.json5
    openquad.container
  records/
    Brewfile
    openclaw.json5
    openquad.container
  documents/
    Brewfile
    openclaw.json5
    openquad.container
  browser-agent/
    Brewfile
    openclaw.json5
    openquad.container
  browser-runtime-headless/
    Brewfile
    openquad.container
  browser-runtime-visible/
    Brewfile
    openquad.container
```

The root `Brewfile` is a local/dev default. CI builds every published image from its template-specific matrix entry.

## Build Agents Locally

Agent images share the OpenClaw/Homebrew base `Containerfile` and select a template with build args:

```bash
podman build \
  -t openquad-comms:dev \
  -f Containerfile \
  --build-arg OPENQUAD_TEMPLATE=communications-calendar \
  --build-arg OPENQUAD_IMAGE_NAME=openquad-comms \
  --build-arg OPENQUAD_VERIFY_TOOLS="himalaya gcalcli vdirsyncer khal khard jq" \
  .
```

Other agent matrix entries use the same `Containerfile`:

```bash
podman build -t openquad-records:dev -f Containerfile \
  --build-arg OPENQUAD_TEMPLATE=records \
  --build-arg OPENQUAD_IMAGE_NAME=openquad-records \
  --build-arg OPENQUAD_LINK_FORMULAE="sqlite libpq" \
  --build-arg OPENQUAD_VERIFY_TOOLS="sqlite3 duckdb jq yq psql" .

podman build -t openquad-documents:dev -f Containerfile \
  --build-arg OPENQUAD_TEMPLATE=documents \
  --build-arg OPENQUAD_IMAGE_NAME=openquad-documents \
  --build-arg OPENQUAD_VERIFY_TOOLS="pandoc pdfinfo pdftotext qpdf tesseract ocrmypdf python3.13 jq" .

podman build -t openquad-browser-agent:dev -f Containerfile \
  --build-arg OPENQUAD_TEMPLATE=browser-agent \
  --build-arg OPENQUAD_IMAGE_NAME=openquad-browser-agent \
  --build-arg OPENQUAD_NPM_PACKAGES="playwright@1.60.0" \
  --build-arg OPENQUAD_VERIFY_TOOLS="jq node npm playwright" .
```

## Worker Contract v0.1

OpenQuad worker images expose a generic worker contract that VIC and other orchestrators can consume. OpenQuad remains a worker/runtime family: it does not own tenants, workflows, approvals, durable records, or canonical audit.

Contract docs:

- [`docs/worker-contract.md`](docs/worker-contract.md)
- [`docs/capability-model.md`](docs/capability-model.md)
- [`docs/orchestrator-integration.md`](docs/orchestrator-integration.md)
- [`docs/vic-integration.md`](docs/vic-integration.md)

Validation and local daemon checks:

```bash
make validate-schemas
make validate-manifests
make test
make test-browser-runtime
```

Run a local worker daemon for one template:

```bash
OPENQUAD_MANIFEST_PATH=templates/documents/openquad.manifest.json \
OPENQUAD_WORKSPACE_DIR=/tmp/openquad-workspace \
uv run --project workerd openquad-workerd
```

The first daemon validates tasks, writes task/result/events/artifact-manifest files, and returns `failed` with `not_implemented` for task types that are declared but do not yet have concrete connector/browser runners. It must not fake successful execution.

## Runtime Layout

OpenQuad agent images follow the live rootless OpenClaw layout:

- `/home/node/.openclaw` is the writable state boundary
- `OPENCLAW_CONFIG_PATH` defaults to `/home/node/.openclaw/openclaw.json`
- `OPENQUAD_DEFAULT_CONFIG` points to `/usr/share/openquad/templates/<template>/openclaw.json5`
- npm, XDG, Codex, and Homebrew caches live under the state tree

Runtime credentials and sync state stay outside the image. Do not bake account credentials, OAuth tokens, browser profiles, or service secrets into images.

## Local Service Topologies

The included Quadlet examples default to a shared user-defined Podman network:

```text
quadlet/openquad.network
templates/*/openquad.container
```

In this mode, sibling services use DNS names such as:

```text
OLLAMA_BASE_URL=http://ollama:11434
SEARXNG_BASE_URL=http://searxng:8080
BROWSER_WS_ENDPOINT=ws://openquad-browser-runtime-headless:3000
BROWSER_CDP_ENDPOINT=http://openquad-browser-runtime-visible:9222
```

`localhost` inside a container means that same container, not sibling services.

## Published Images

GitHub Actions builds and publishes all matrix images to GHCR on pushes to `main`, version tags, scheduled rebuilds, and manual workflow runs. Pull requests build images without publishing them.

## Template Expansion Rule

When adding future OpenQuad templates, create a narrow `templates/<purpose>/` directory with a purpose-built Brewfile, starter config, runtime example, explicit policy boundaries, and an expected output contract. Do not grow any OpenQuad image into a broad Hermes replacement.
