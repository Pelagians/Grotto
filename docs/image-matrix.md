# Grotto Image Matrix

This document describes the specialized AI agent runtimes in the Grotto ecosystem.

## Runtime Images

| Image | Purpose | Key Capabilities |
| --- | --- | --- |
| `ghcr.io/pelagians/grotto-comms:latest` | Communications & Calendar | Email, messaging, calendar, reminders, contacts, scheduling, follow-up |
| `ghcr.io/pelagians/grotto-records:latest` | Structured Records | Business records with database support (Postgres, SQLite, JSON, CSV) |
| `ghcr.io/pelagians/grotto-documents:latest` | Document Processing | Read, classify, OCR, extract, convert, draft, organize documents |
| `ghcr.io/pelagians/grotto-browser-agent:latest` | Browser Automation | Browser workflows through separate browser runtime containers |

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

## Design Constraints

All Grotto runtimes follow these constraints:

1. **Narrow scope**: Each runtime does one thing well
2. **Auditable writes**: All write operations are logged
3. **Bounded autonomy**: Autonomous writes allowed only when bounded by policy
4. **No destructive actions**: Destructive, financial, security-sensitive, external-communication, or irreversible actions require confirmation or are blocked by default
5. **Portable**: Run anywhere OCI containers run
6. **Reproducible**: Same inputs produce same outputs

## Template Expansion

When adding new Grotto runtimes:

1. Create a narrow `templates/<purpose>/` directory
2. Include purpose-built Brewfile with required tools
3. Provide starter configuration
4. Define explicit policy boundaries
5. Specify expected output contract
6. Document allowed tools and out-of-scope actions

Do not grow any Grotto runtime into a broad general-purpose agent.
