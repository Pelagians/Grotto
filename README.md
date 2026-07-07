# Grotto

Grotto is a curated ecosystem of specialized AI agent runtimes packaged as portable OCI containers.

Each runtime is narrow, focused, and designed for one constrained job. Grotto agents are specialized workers, not general-purpose AI platforms.

## What Grotto Is

- Specialized AI agent runtimes
- Portable OCI containers
- Reproducible builds
- Sane defaults
- Runtime-agnostic (if it runs in OCI, it can be a Grotto runtime)

## What Grotto Is Not

- An AI framework
- An LLM
- An orchestration platform
- A chatbot system
- A general-purpose AI assistant

## Current Runtimes

| Image | Purpose |
| --- | --- |
| `ghcr.io/pelagians/grotto-comms:latest` | Email, messaging, calendar, reminders, contacts, scheduling |
| `ghcr.io/pelagians/grotto-records:latest` | Structured business records with database support |
| `ghcr.io/pelagians/grotto-documents:latest` | Document processing: read, classify, OCR, extract, convert |
| `ghcr.io/pelagians/grotto-browser-agent:latest` | Browser automation through separate browser runtimes |

See [`docs/image-matrix.md`](docs/image-matrix.md) for detailed capabilities, permissions, and output contracts.

## Design Principles

- **OCI-first**: Containers are the primary deployment artifact
- **Container-native**: Built to run as containers, not adapted to them
- **Reproducible**: Same inputs produce same outputs
- **Versioned**: Explicit versions for reproducibility
- **Portable**: Run anywhere OCI containers run
- **Runtime-focused**: Each runtime does one thing well
- **Curated quality**: Official runtimes maintained to high standards

## Build

Agent images use a shared Containerfile with template-specific build args:

```bash
podman build \
  -t grotto-comms:dev \
  -f Containerfile \
  --build-arg GROTTO_TEMPLATE=communications-calendar \
  --build-arg GROTTO_IMAGE_NAME=grotto-comms \
  --build-arg GROTTO_VERIFY_TOOLS="himalaya gcalcli vdirsyncer khal khard jq" \
  .
```

Other runtimes use the same pattern:

```bash
# Records agent
podman build -t grotto-records:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=records \
  --build-arg GROTTO_IMAGE_NAME=grotto-records \
  --build-arg GROTTO_LINK_FORMULAE="sqlite libpq" \
  --build-arg GROTTO_VERIFY_TOOLS="sqlite3 duckdb jq yq psql" .

# Documents agent
podman build -t grotto-documents:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=documents \
  --build-arg GROTTO_IMAGE_NAME=grotto-documents \
  --build-arg GROTTO_VERIFY_TOOLS="pandoc pdfinfo pdftotext qpdf tesseract ocrmypdf python3.13 jq" .

# Browser agent
podman build -t grotto-browser-agent:dev -f Containerfile \
  --build-arg GROTTO_TEMPLATE=browser-agent \
  --build-arg GROTTO_IMAGE_NAME=grotto-browser-agent \
  --build-arg GROTTO_NPM_PACKAGES="playwright@1.60.0" \
  --build-arg GROTTO_VERIFY_TOOLS="jq node npm playwright" .
```

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
```

Each template contains:
- Purpose-built Brewfile with required tools
- Starter configuration
- Runtime example
- Explicit policy boundaries
- Expected output contract

## Worker Contract

Grotto runtimes expose a generic worker contract for orchestrators. Grotto remains a runtime layer: it does not own tenants, workflows, approvals, durable records, or canonical audit.

Contract documentation:
- [`docs/worker-contract.md`](docs/worker-contract.md)
- [`docs/capability-model.md`](docs/capability-model.md)
- [`docs/orchestrator-integration.md`](docs/orchestrator-integration.md)
- [`docs/nereus-integration.md`](docs/nereus-integration.md)

## Runtime Layout

Grotto agent images follow a rootless layout:

- `/home/node/.openclaw` is the writable state boundary
- `OPENCLAW_CONFIG_PATH` defaults to `/home/node/.openclaw/openclaw.json`
- `GROTTO_DEFAULT_CONFIG` points to `/usr/share/grotto/templates/<template>/openclaw.json5`

Runtime credentials and sync state stay outside the image. Do not bake account credentials, OAuth tokens, browser profiles, or secrets into images.

## Browser Integration

The browser agent connects to separate browser runtime containers:

```text
BROWSER_WS_ENDPOINT=ws://browser-runtime-headless:3000
BROWSER_CDP_ENDPOINT=http://browser-runtime-visible:9222
```

Browser runtimes are maintained in the [web-apps repository](https://github.com/pelagians/web-apps).

## Published Images

GitHub Actions builds and publishes all runtime images to GHCR on:
- Pushes to `main`
- Version tags
- Scheduled rebuilds
- Manual workflow runs

Pull requests build images without publishing them.

## Adding New Runtimes

When adding future Grotto runtimes, create a narrow `templates/<purpose>/` directory with:
- Purpose-built Brewfile
- Starter configuration
- Runtime example
- Explicit policy boundaries
- Expected output contract

Do not grow any Grotto runtime into a broad general-purpose agent.

## Relationship to Pelagian Ecosystem

Grotto is one of the open-source foundations of the Pelagian ecosystem:

- **Current** provides the operating system
- **Grotto** provides specialized AI workers
- **Cage** provides Windows compatibility workers
- **Nereus** deploys and orchestrates Grotto workers
- **Nyra** interacts with Nereus, not directly with Grotto

Grotto is fully usable without Nereus. Users can pull and run Grotto containers independently.

## License

See [LICENSE](LICENSE) for details.
