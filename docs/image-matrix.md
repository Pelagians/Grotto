# OpenQuad Image Matrix

OpenQuad is the product/family name for a four-agent starter bundle plus two browser runtime images. OpenQuad agents are narrow workers, not mini-Hermes instances.

## Published images

| Image | Kind | Build file | Template | Purpose |
| --- | --- | --- | --- | --- |
| `ghcr.io/myos-dev/openquad-comms:latest` | OpenClaw agent | `Containerfile` | `communications-calendar` | Email, messaging, calendar, reminders, contacts, scheduling, follow-up |
| `ghcr.io/myos-dev/openquad-records:latest` | OpenClaw agent | `Containerfile` | `records` | Structured business records, VIC/API/Postgres/SQLite/JSON/CSV |
| `ghcr.io/myos-dev/openquad-documents:latest` | OpenClaw agent | `Containerfile` | `documents` | Read/classify/OCR/extract/convert/draft/organize documents |
| `ghcr.io/myos-dev/openquad-browser-agent:latest` | OpenClaw agent | `Containerfile` | `browser-agent` | Policy-bounded browser workflows via separate browser runtimes |
| `ghcr.io/myos-dev/openquad-browser-runtime-headless:latest` | Browser runtime | `Containerfile.browser-runtime-headless` | `browser-runtime-headless` | Playwright WebSocket browser runtime for repeatable headless workflows |
| `ghcr.io/myos-dev/openquad-browser-runtime-visible:latest` | Browser runtime | `Containerfile.browser-runtime-visible` | `browser-runtime-visible` | Visible/VNC/noVNC Chromium runtime for login, teaching, and debugging |

## Agent policy summary

| Agent | Data surfaces | Autonomous writes | Requires approval / blocked by default | Web policy |
| --- | --- | --- | --- | --- |
| Communications | email, messaging connectors, calendars, contacts, reminders | draft replies, prepare scheduling options, low-risk organization | sending external messages, attendee meeting changes, deletes, financial/security actions | light/contextual search and fetch |
| Records | VIC API/resources, Postgres, SQLite, local JSON/CSV, later Sheets/CRM | low-risk create/update with evidence/provenance | deletes, external comms, payments, browser actions, freeform research | no broad research; connector/API enrichment only |
| Documents | local mounted files first, later Drive/WebDAV/Notion/Obsidian | extracted JSON/CSV, summaries, conversions, safe renames/classification in managed folders | editing authoritative docs, overwrites, sensitive deletion | fetch/download only; no broad research |
| Browser agent | internal browser runtime WS/CDP, approved web workflows, artifacts | navigate/read/search allowed sites, extract, download, fill forms, managed uploads | payments, purchases, security settings, destructive admin, high-risk submits, mass scraping, captcha-solving, credential harvesting | browser-mediated and allowlist restricted |

## Browser runtime split

`openquad-browser-agent` must stay small and independently upgradable. It contains OpenClaw agent logic, model config, prompt/policy, and Playwright client tooling. It does **not** contain full browser stacks.

Browser stacks live in runtime-only images:

- `openquad-browser-runtime-headless` exposes a Playwright WebSocket endpoint for repeatable headless workflows.
- `openquad-browser-runtime-visible` exposes Chromium CDP plus VNC/noVNC for login, teaching, debugging, and user-assisted workflows with a persistent browser profile.

Both runtimes keep the default bundled Playwright Chromium path but accept browser-family-agnostic aliases such as `BROWSER_EXECUTABLE_PATH`, `PLAYWRIGHT_BROWSER_CHANNEL`, `BROWSER_CDP_HOST`, and `BROWSER_EXTRA_ARGS`. See [`browser-runtime-contract.md`](browser-runtime-contract.md).

Browser-control endpoints are privileged. They must not be publicly exposed. In Kubernetes, expose them only inside the cluster via Service DNS and restrict access with NetworkPolicy so only `openquad-browser-agent` and trusted control-plane components can connect.

## Output contracts

Every agent output should carry an explicit policy decision, evidence, and provenance.

- Communications: `action`, `target`, `draft_or_result`, `policy_decision`, `evidence`, `provenance`
- Records: `operation`, `record_type`, `record_id`, `policy_decision`, `evidence`, `provenance`
- Documents: `source`, `classification`, `outputs`, `policy_decision`, `evidence`, `provenance`
- Browser agent: `workflow`, `target`, `actions`, `artifacts`, `policy_decision`, `evidence`, `provenance`

## Template layout

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

The root `Brewfile` is a local/dev default. CI builds each image from its template-specific build target.
