# Grotto

Grotto is the product/family name for a four-agent starter bundle of minimal OpenClaw container templates plus split browser runtimes. The design goal is the opposite of a large do-everything Hermes context: each Grotto agent should be small, connected to a small local model when possible, and equipped with only the tools needed for one constrained job.

Grotto agents are narrow workers, not mini-Hermes instances. All writes should be auditable. Autonomous writes are allowed only when bounded by policy. Destructive, financial, security-sensitive, external-communication, or irreversible actions require confirmation or are blocked by default.

## Image Matrix

| Image | Kind | Purpose |
| --- | --- | --- |
| `ghcr.io/myos-dev/grotto-comms:latest` | OpenClaw agent | Email, messaging, calendar, reminders, contacts, scheduling, follow-up |
| `ghcr.io/myos-dev/grotto-records:latest` | OpenClaw agent | Structured business records with Nereus/Postgres/SQLite/JSON/CSV support |
| `ghcr.io/myos-dev/grotto-documents:latest` | OpenClaw agent | Read, classify, OCR, extract, convert, draft, and organize documents |
| `ghcr.io/myos-dev/grotto-browser-agent:latest` | OpenClaw agent | Browser workflows through separate browser runtime containers |

See [`docs/image-matrix.md`](docs/image-matrix.md) for the detailed data surfaces, permissions, allowed tools, out-of-scope actions, and output contracts.

## Template Layout

```text
templates/
  communications-calendar/
    Brewfile
    openclaw.json5
    grotto.container
  records/
    Brewfile
    openclaw.json5
    grotto.container
  documents/
    Brewfile
    openclaw.json5
    grotto.container
  browser-agent/
    Brewfile
    openclaw.json5
    grotto.container
  browser-runtime-headless/
    Brewfile
    grotto.container
  browser-runtime-visible/
    Brewfile
    grotto.container
```

The root `Brewfile` is a local/dev default. CI builds every published image from its template-specific matrix entry.

## Build Agents Locally

Agent images share the OpenClaw/Homebrew base `Containerfile` and select a template with build args:

```bash
podman build \
  -t grotto-comms:dev \
  -f Containerfile \
  --build-arg GROTTO_TEMPLATE=communications-calendar \
  --build-arg GROTTO_IMAGE_NAME=grotto-comms \
  --build-arg GROTTO_VERIFY_TOOLS="himalaya gcalcli vdirsyncer khal khard jq" \
  .
```

Other agent matrix entries use the same `Containerfile`:

```bash
podman build -t grotto-records:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=records \
  --build-arg GROTTO_IMAGE_NAME=grotto-records \
  --build-arg GROTTO_LINK_FORMULAE="sqlite libpq" \
  --build-arg GROTTO_VERIFY_TOOLS="sqlite3 duckdb jq yq psql" .

podman build -t grotto-documents:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=documents \
  --build-arg GROTTO_IMAGE_NAME=grotto-documents \
  --build-arg GROTTO_VERIFY_TOOLS="pandoc pdfinfo pdftotext qpdf tesseract ocrmypdf python3.13 jq" .

podman build -t grotto-browser-agent:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=browser-agent \
  --build-arg GROTTO_IMAGE_NAME=grotto-browser-agent \
  --build-arg GROTTO_NPM_PACKAGES="playwright@1.60.0" \
  --build-arg GROTTO_VERIFY_TOOLS="jq node npm playwright" .
```

## Worker Contract v0.1

Grotto worker images expose a generic worker contract that Nereus and other orchestrators can consume. Grotto remains a worker/runtime family: it does not own tenants, workflows, approvals, durable records, or canonical audit.

Contract docs:

- [`docs/worker-contract.md`](docs/worker-contract.md)
- [`docs/capability-model.md`](docs/capability-model.md)
- [`docs/orchestrator-integration.md`](docs/orchestrator-integration.md)
- [`docs/nereus-integration.md`](docs/nereus-integration.md)

Validation and local daemon checks:

```bash
make validate-schemas
make validate-manifests
make test
make test-browser-runtime
```

Run a local worker daemon for one template:

```bash
GROTTO_MANIFEST_PATH=templates/documents/grotto.manifest.json \
GROTTO_WORKSPACE_DIR=/tmp/grotto-workspace \
uv run --project workerd grotto-workerd
```

The first daemon validates tasks, writes task/result/events/artifact-manifest files, and returns `failed` with `not_implemented` for task types that are declared but do not yet have concrete connector/browser runners. It must not fake successful execution.

## Runtime Layout

Grotto agent images follow the live rootless OpenClaw layout:

- `/home/node/.openclaw` is the writable state boundary
- `OPENCLAW_CONFIG_PATH` defaults to `/home/node/.openclaw/openclaw.json`
- `GROTTO_DEFAULT_CONFIG` points to `/usr/share/grotto/templates/<template>/openclaw.json5`
- npm, XDG, Codex, and Homebrew caches live under the state tree

Runtime credentials and sync state stay outside the image. Do not bake account credentials, OAuth tokens, browser profiles, or sernereuse secrets into images.

## Local Sernereuse Topologies

The included Quadlet examples default to a shared user-defined Podman network:

```text
quadlet/grotto.network
templates/*/grotto.container
```

In this mode, sibling sernereuses use DNS names such as:

```text
OLLAMA_BASE_URL=http://ollama:11434
SEARXNG_BASE_URL=http://searxng:8080
BROWSER_WS_ENDPOINT=ws://grotto-browser-runtime-headless:3000
BROWSER_CDP_ENDPOINT=http://grotto-browser-runtime-visible:9222
```

`localhost` inside a container means that same container, not sibling sernereuses.

## Published Images

GitHub Actions builds and publishes all matrix images to GHCR on pushes to `main`, version tags, scheduled rebuilds, and manual workflow runs. Pull requests build images without publishing them.

## Template Expansion Rule

When adding future Grotto templates, create a narrow `templates/<purpose>/` directory with a purpose-built Brewfile, starter config, runtime example, explicit policy boundaries, and an expected output contract. Do not grow any Grotto image into a broad Hermes replacement.
