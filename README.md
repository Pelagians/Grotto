# Grotto

Grotto is a curated ecosystem of specialized AI runtimes packaged as portable OCI containers.

Most Grotto images are narrow worker agents. Interactive images remain single-purpose workbenches rather than general desktop environments.

## What Grotto Is

- Specialized worker and workbench runtimes
- Portable OCI containers
- Reproducible build definitions
- Sane defaults
- Runtime-agnostic infrastructure when the workload fits OCI
- A curated runtime layer for Pelagian and independent deployments

## What Grotto Is Not

- An AI framework
- An LLM
- An orchestration platform
- A monolithic assistant product
- A tenant, workflow, or audit system

## Current Runtimes

| Image | Purpose |
| --- | --- |
| `ghcr.io/pelagians/grotto-comms:latest` | Email, messaging, calendar, reminders, contacts, scheduling |
| `ghcr.io/pelagians/grotto-records:latest` | Structured business records with database support |
| `ghcr.io/pelagians/grotto-documents:latest` | Document processing: read, classify, OCR, extract, convert |
| `ghcr.io/pelagians/grotto-browser-agent:latest` | Browser automation through separate browser runtimes |
| `ghcr.io/pelagians/grotto-chatgpt-desktop:latest` | Selkies-streamed ChatGPT and Codex desktop workbench |

See [`docs/image-matrix.md`](docs/image-matrix.md) for detailed capabilities, permissions, and output contracts.

## Design Principles

- **OCI-first**: Containers are the primary deployment artifact
- **Container-native**: New runtimes should be designed around container boundaries
- **Build-time assembly**: Applications and dependencies are assembled before runtime
- **Versioned**: Explicit versions and source revisions where possible
- **Portable**: Run anywhere compatible OCI containers run
- **Runtime-focused**: Each image has a defined purpose and state boundary
- **Curated quality**: Official runtimes are maintained to consistent standards

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

Other agent runtimes use the same pattern:

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

The ChatGPT desktop workbench uses a dedicated multi-stage build because it is
an interactive Selkies application rather than an OpenClaw worker:

```bash
podman build \
  -t grotto-chatgpt-desktop:dev \
  -f Containerfile.chatgpt-desktop \
  .
```

See [`docs/chatgpt-desktop.md`](docs/chatgpt-desktop.md) for CI, runtime, storage,
security, and publication details.

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

runtimes/
  chatgpt-desktop/
    root/
      defaults/
        autostart
```

Agent templates contain:

- Purpose-built Brewfile with required tools
- Starter configuration
- Runtime example
- Explicit policy boundaries
- Expected output contract

Interactive runtimes use their own Containerfile and document their state,
network, display, and authentication boundaries.

## Worker Contract

Grotto worker images expose a generic worker contract for orchestrators. Grotto remains a runtime layer: it does not own tenants, workflows, approvals, durable records, or canonical audit.

Interactive workbench images such as `grotto-chatgpt-desktop` do not implement
the worker contract.

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

The ChatGPT desktop runtime uses:

- `/config` for authenticated application and Codex state
- `/workspace` for the mounted project workspace
- port `3001` for Selkies HTTPS

Runtime credentials and sync state stay outside images. Do not bake account
credentials, OAuth tokens, browser profiles, or secrets into images.

## Browser Integration

The browser agent connects to separate browser runtime containers:

```text
BROWSER_WS_ENDPOINT=ws://browser-runtime-headless:3000
BROWSER_CDP_ENDPOINT=http://browser-runtime-visible:9222
```

Browser runtimes are maintained in the [web-apps repository](https://github.com/pelagians/web-apps).

## Published Images

GitHub Actions builds and publishes all Grotto images to GHCR on:

- pushes to `main`
- version tags
- scheduled rebuilds
- manual workflow runs

Pull requests build every matrix entry without publishing it. The ChatGPT
desktop image is part of the same matrix and follows the same tags and
publication rules as the agent images.

GHCR publication and package visibility are separate: the workflow creates or
updates the package, while public or private visibility is managed in the
organization's package settings.

## Adding New Runtimes

For worker agents, create a narrow `templates/<purpose>/` directory with:

- Purpose-built Brewfile
- Starter configuration
- Runtime example
- Explicit policy boundaries
- Expected output contract

For interactive or non-OpenClaw runtimes:

- Use a dedicated Containerfile
- Build application payloads before runtime
- Document persistent state and exposed ports
- Define whether the image implements the worker contract
- Keep the application surface single-purpose
- Review upstream redistribution terms before publication

Do not grow a Grotto runtime into a broad general-purpose desktop.

## Relationship to Pelagian Ecosystem

Grotto is one of the open-source foundations of the Pelagian ecosystem:

- **Current** provides the operating system
- **Grotto** provides specialized AI workers and workbench runtimes
- **Cage** provides Windows compatibility workers
- **Nereus** deploys and orchestrates Grotto workers
- **Nyra** interacts with Nereus, not directly with Grotto

Grotto is fully usable without Nereus. Users can build and run Grotto
containers independently.

## License

See [LICENSE](LICENSE) for Grotto source licensing. Upstream applications built
by individual runtime definitions retain their own licenses and distribution
terms.
