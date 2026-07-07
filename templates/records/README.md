# grotto-records

Structured business-records OpenClaw agent. Nereus durable records are the ideal backend, but this image stays generic enough for Postgres, SQLite, JSON/CSV, and later Sheets/CRM connectors.

## Scope

In scope: JSON API resources, Postgres-backed records, SQLite staging, local JSON/CSV import/export, low-risk create/update operations, and evidence/provenance for every write.

Out of scope: destructive deletes by default, external communications, payments, browser actions, freeform web research, email/calendar workflows, and document OCR.

## Mutation model

Low-risk autonomous record create/update is allowed when policy permits it. Bulk updates, schema changes, and Nereus mutations should carry explicit policy decisions and evidence. Deletes are blocked by default.

## Expected output contract

Results should include `operation`, `record_type`, `record_id`, `policy_decision`, `evidence`, and `provenance`.
