# Grotto Image Matrix

Grotto provides specialized AI agent containers. Each agent is a narrow, focused worker designed for specific tasks.

## Agent Images

| Image | Purpose |
| --- | --- |
| `ghcr.io/pelagians/grotto-comms:latest` | Communications/calendar agent for email, messaging, calendar, reminders, and contacts |
| `ghcr.io/pelagians/grotto-records:latest` | Records agent for structured business records with VIC/Postgres/SQLite/JSON/CSV support |
| `ghcr.io/pelagians/grotto-documents:latest` | Documents agent for OCR, extraction, conversion, classification, and managed document organization |
| `ghcr.io/pelagians/grotto-browser-agent:latest` | Browser workflow agent that controls separate browser runtime containers |

## Browser Runtime Images

Browser runtime containers are maintained in the separate **web-apps** repository:

- `ghcr.io/pelagians/web-apps-browser-runtime-chromium-headless`
- `ghcr.io/pelagians/web-apps-browser-runtime-chromium-headful`
- `ghcr.io/pelagians/web-apps-browser-runtime-chrome-headless`
- `ghcr.io/pelagians/web-apps-browser-runtime-chrome-headful`
- `ghcr.io/pelagians/web-apps-browser-runtime-edge-headless`
- `ghcr.io/pelagians/web-apps-browser-runtime-edge-headful`
- `ghcr.io/pelagians/web-apps-browser-runtime-brave-headless`
- `ghcr.io/pelagians/web-apps-browser-runtime-brave-headful`

See the web-apps repository for browser runtime documentation.

## Agent Design Principles

Each Grotto agent follows these principles:

1. **Narrow focus**: Each agent is designed for a specific task domain
2. **Small context**: Agents work with minimal context to reduce token usage
3. **Auditable writes**: All writes are logged and reviewable
4. **Bounded autonomy**: Autonomous writes are allowed only when bounded by policy
5. **Confirmation required**: Destructive, financial, security-sensitive, external-communication, or irreversible actions require confirmation or are blocked by default

## Integration

Agents connect to external services and runtimes through well-defined contracts:

- **Browser agent** connects to web-apps browser runtimes over internal networking
- **Records agent** connects to databases and storage systems
- **Documents agent** connects to document storage and processing services
- **Communications agent** connects to email, calendar, and messaging services

All agent-to-runtime communication follows the worker contract defined in `docs/worker-contract.md`.
