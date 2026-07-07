# grotto-documents

Document-processing OpenClaw agent for reading, classifying, OCR, extracting, converting, drafting, and organizing documents.

## Scope

In scope: local mounted files first; PDFs, images/scans, docx, xlsx, pptx, markdown, plain text, HTML, and CSV. Google Drive/Docs, WebDAV/Nextcloud, Notion, and Obsidian are later connector targets.

Out of scope: email/messaging, calendar scheduling, business-record mutation, browser automation, sensitive deletion, and irreversible deletion.

## Mutation model

Autonomous writes are allowed inside managed document/workspace folders for extracted JSON, CSV, summaries, converted files, renamed files, and classified folder structures. Editing authoritative source documents requires approval unless explicitly marked safe.

## Expected output contract

Results should include `source`, `classification`, `outputs`, `policy_decision`, `evidence`, and `provenance`.
