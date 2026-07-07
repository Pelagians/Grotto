
# Grotto Worker Contract v0.1

Grotto is a generic deployable worker family. It is not inherently tied to Nereus and it does not own tenants, workflows, approvals, durable records, or audit source-of-truth.

Grotto workers accept bounded typed task envelopes, execute one task at a time from an external orchestrator, and return structured results, artifacts, and local events. The orchestrator remains responsible for scheduling, policy authority, approvals, durable status, and audit.

## Contract shape

```text
External orchestrator
  -> policy decision
  -> Grotto task envelope
  -> Grotto structured result/artifacts/events
  -> orchestrator durable task status/audit/continuation
```

Grotto workers must not form an uncontrolled peer-to-peer agent swarm. A worker may call connector APIs or browser runtimes needed for its own bounded task, but it should not delegate orchestration authority to another worker.

## Required endpoints

Every Grotto worker daemon exposes:

```text
GET  /healthz
GET  /readyz
GET  /grotto/v1/manifest
GET  /grotto/v1/capabilities
POST /grotto/v1/tasks
GET  /grotto/v1/tasks/{task_id}
POST /grotto/v1/tasks/{task_id}/cancel
GET  /grotto/v1/tasks/{task_id}/artifacts
```

## Task envelope

Task envelopes are validated against `schemas/grotto-task.schema.json`. They include:

- `task_id`: orchestrator-supplied task identity
- `idempotency_key`: stable retry key
- `capability`: advertised capability such as `documents.convert`
- `task_type`: concrete task type supported by the capability
- `input`: task-specific payload
- `constraints`: runtime/network/write constraints
- `policy`: policy decision already made by the orchestrator
- `provenance`: source/orchestrator context

Grotto respects policy decisions in the envelope, but it does not make final policy decisions for an external control plane.

## Result envelope

Results are validated against `schemas/grotto-task-result.schema.json`. They include:

- status: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `requires_approval`, or `rejected`
- `worker`, `capability`, and `task_type`
- structured `result`
- the policy decision that was used
- evidence/provenance
- artifacts
- errors

If a task type is accepted by a manifest but not implemented by the current runner, the worker returns `failed` with an error code such as `not_implemented`. It must not pretend success.

## Local task layout

Every task uses this local layout:

```text
/home/node/.openclaw/workspace/tasks/<task_id>/
  task.json
  result.json
  events.jsonl
  artifacts/
  artifact-manifest.json
```

`GROTTO_WORKSPACE_DIR` can override `/home/node/.openclaw/workspace` for local development and tests.

## Artifact contract

Artifacts must be described by `schemas/grotto-artifact-manifest.schema.json` and include:

```json
{
  "kind": "text|json|csv|pdf|png|html|trace|screenshot|other",
  "uri": "file:///...",
  "sha256": "...",
  "size_bytes": 123,
  "content_type": "string"
}
```

Grotto stores local file URIs. External orchestrators decide whether to copy, persist, redact, or expose those artifacts.

## Event contract

Events are JSONL entries validated by `schemas/grotto-event.schema.json`. Common event types are:

```json
{"event_type":"task.accepted","task_id":"...","created_at":"..."}
{"event_type":"task.started","task_id":"...","created_at":"..."}
{"event_type":"artifact.created","task_id":"...","created_at":"...","event_json":{}}
{"event_type":"task.succeeded","task_id":"...","created_at":"..."}
```

Events are local worker evidence, not an orchestrator's canonical audit log.
