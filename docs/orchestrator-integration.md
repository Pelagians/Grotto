
# Orchestrator Integration

Grotto is useful with Nereus or any other orchestrator that can call a stable worker HTTP API.

## Generic flow

```text
Orchestrator task
  -> orchestrator policy evaluation
  -> Grotto task envelope
  -> Grotto result/artifacts/events
  -> orchestrator status/audit/next step
```

## Registration

An orchestrator should register worker `base_url`, call `/grotto/v1/manifest`, store the manifest, and use `/grotto/v1/capabilities` for routing.

## Submission

The orchestrator submits `POST /grotto/v1/tasks` only after policy has allowed the task. If policy requires approval, the orchestrator should create its approval object and wait. If policy rejects the task, the orchestrator should not call Grotto.

## Idempotency

Use a stable `idempotency_key` so retries can be associated with the same logical task. The first daemon stores tasks under the supplied `task_id`; future versions may use idempotency for dedupe/resume.

## Artifact handling

Grotto artifact URIs are local to the worker. Orchestrators should copy or ingest artifacts they need as durable evidence, verify checksums, redact sensitive content where needed, and store only approved metadata in their canonical audit trail.

## Non-goals

Grotto does not provide:

- tenant ownership
- workflow orchestration
- approvals
- durable business records
- canonical audit logs
- marketplace/runtime scheduling
- connector secret storage
