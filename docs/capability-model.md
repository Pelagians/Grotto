
# OpenQuad Capability Model v0.1

OpenQuad workers advertise capabilities through `openquad.manifest.json`. A capability is a generic bounded action that an orchestrator can route to a worker.

## Manifest requirements

Each worker manifest declares:

- worker name
- OpenQuad contract version
- image name
- template name
- capabilities
- supported task types
- side-effect classes
- required and optional environment variable names
- artifact types
- policy hints
- out-of-scope actions

The manifest is intentionally generic. It does not contain tenant IDs, workflow IDs, customer secrets, approvals, or VIC-only concepts.

## Capability naming

Capability names use stable dotted names:

- `comms.read`
- `comms.classify`
- `comms.draft_reply`
- `records.match`
- `documents.convert`
- `browser.screenshot`

Task types are concrete operations below a capability, for example `documents.convert` may support `convert_pdf_to_text`.

## Side-effect classes

Workers describe side effects so orchestrators can make policy decisions. Common side-effect classes are:

- `read_only`
- `local_artifact_write`
- `external_mutation`
- `external_message`
- `credential_use`
- `browser_control`
- `file_download`
- `file_upload`

OpenQuad provides these as hints only. External orchestrators decide final policy.

## Policy hint boundaries

OpenQuad manifests may say that sending messages, mutating external systems, or using credentials should require approval, but OpenQuad does not approve its own work. It can reject obviously unsafe or unsupported tasks locally, yet final policy authority belongs to the caller.
