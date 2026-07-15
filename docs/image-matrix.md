# Grotto Image Matrix

This document describes the specialized AI runtimes in the Grotto ecosystem.

## Worker Images

| Image | Purpose | Key Capabilities |
| --- | --- | --- |
| `ghcr.io/pelagians/grotto-comms:latest` | Communications & Calendar | Email, messaging, calendar, reminders, contacts, scheduling, follow-up |
| `ghcr.io/pelagians/grotto-records:latest` | Structured Records | Business records with database support (Postgres, SQLite, JSON, CSV) |
| `ghcr.io/pelagians/grotto-documents:latest` | Document Processing | Read, classify, OCR, extract, convert, draft, organize documents |
| `ghcr.io/pelagians/grotto-browser-agent:latest` | Browser Automation | Browser workflows through separate browser runtime containers |

## Interactive Runtime Images

| Image | Purpose | Key Capabilities |
| --- | --- | --- |
| `ghcr.io/pelagians/grotto-chatgpt-desktop:latest` | ChatGPT and Codex Workbench | Selkies-streamed desktop UI, Codex CLI, persistent application state, mounted workspace |

`grotto-chatgpt-desktop` is an interactive application runtime. It does not
implement the Grotto worker contract. See
[`docs/chatgpt-desktop.md`](chatgpt-desktop.md).

## Browser Runtimes

Browser runtimes are maintained separately in the [web-apps repository](https://github.com/pelagians/web-apps).

The browser agent connects to browser runtimes via:

- `BROWSER_WS_ENDPOINT` - WebSocket endpoint for headless browser
- `BROWSER_CDP_ENDPOINT` - Chrome DevTools Protocol endpoint for visible browser

See [web-apps image matrix](https://github.com/pelagians/web-apps/blob/main/docs/image-matrix.md) for browser runtime details.

## Runtime Capabilities

### grotto-comms

**Data surfaces:**

- Email (IMAP/SMTP via himalaya)
- Calendar (Google Calendar via gcalcli, CalDAV via vdirsyncer/khal)
- Contacts (CardDAV via vdirsyncer/khard)

**Allowed tools:**

- himalaya, gcalcli, vdirsyncer, khal, khard, jq

**Out of scope:**

- Direct database writes
- File system operations outside workspace
- Network access beyond configured endpoints

**Output contract:**

- Structured JSON responses
- Audit trail for all actions
- Error messages with context

### grotto-records

**Data surfaces:**

- SQLite databases
- PostgreSQL databases
- JSON files
- CSV files

**Allowed tools:**

- sqlite3, duckdb, jq, yq, psql

**Out of scope:**

- Email sending
- Calendar operations
- Document processing

**Output contract:**

- Query results in requested format
- Transaction logs
- Schema validation

### grotto-documents

**Data surfaces:**

- PDF files
- Office documents (DOCX, XLSX, PPTX)
- Plain text files
- Images (for OCR)

**Allowed tools:**

- pandoc, pdfinfo, pdftotext, qpdf, tesseract, ocrmypdf, python3.13, jq

**Out of scope:**

- Email operations
- Database queries
- Calendar management

**Output contract:**

- Extracted text in structured format
- Document metadata
- Conversion results with status

### grotto-browser-agent

**Data surfaces:**

- Web pages via browser runtime
- Screenshots and DOM snapshots

**Allowed tools:**

- jq, node, npm, playwright

**Out of scope:**

- Direct browser execution (delegated to browser runtimes)
- File system operations outside workspace
- Direct network requests (must go through browser)

**Output contract:**

- Browser action results
- Screenshot paths
- Extracted data in structured format

### grotto-chatgpt-desktop

**Data surfaces:**

- ChatGPT Desktop authenticated state under `/config`
- Codex configuration and credentials under `/config/.codex`
- Project files mounted at `/workspace`
- Selkies HTTPS interface on port `3001`

**Included tools and services:**

- ChatGPT Desktop Linux wrapper output
- Codex CLI
- Selkies
- X11 and Wayland-compatible Electron runtime
- optional Intel or AMD render-node access

**Out of scope:**

- Grotto worker-contract task dispatch
- Nereus orchestration and durable workflow state
- Automatic account authentication
- Public internet exposure without an application gateway
- Baked credentials or project data

**Runtime contract:**

- interactive single-application desktop
- persistent `/config` state
- persistent or bind-mounted `/workspace`
- build-time application assembly
- no runtime npm installation or DMG extraction

## Design Constraints

All Grotto runtimes follow these constraints:

1. **Narrow scope**: Each runtime has a defined purpose and state boundary.
2. **Build-time assembly**: Applications and dependencies are assembled before startup.
3. **Explicit contracts**: Each image states whether it is a worker or interactive runtime.
4. **Bounded autonomy**: Autonomous writes are allowed only when bounded by policy.
5. **No destructive defaults**: Destructive, financial, security-sensitive, external-communication, or irreversible actions require confirmation or are blocked by default.
6. **Portable**: Images run on compatible OCI engines.
7. **Versioned**: Build definitions pin source revisions where practical.
8. **Credential separation**: Authentication state remains in mounted storage, never image layers.

## Runtime Expansion

When adding a worker runtime:

1. Create a narrow `templates/<purpose>/` directory.
2. Include a purpose-built Brewfile with required tools.
3. Provide starter configuration.
4. Define explicit policy boundaries.
5. Specify the expected output contract.
6. Document allowed tools and out-of-scope actions.

When adding an interactive runtime:

1. Use a dedicated Containerfile.
2. Define persistent state and workspace mounts.
3. Document display, network, and authentication boundaries.
4. Build application payloads before runtime.
5. State explicitly that the worker contract is not implemented unless it actually is.
6. Review upstream redistribution rights before enabling publication.

Do not grow any Grotto runtime into a broad general-purpose desktop.
