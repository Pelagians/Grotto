
# Nereus Integration

Nereus can ingest Grotto workers as external task executors, but Grotto remains a generic worker family.

## Boundary

```text
Nereus WorkflowRun
  -> Nereus Task
  -> Nereus policy evaluation
  -> Grotto worker task API
  -> Grotto structured result/artifacts/events
  -> Nereus task status/audit/workflow continuation
```

Nereus remains the control plane. It owns tenants, workflows, approvals, durable status, records, audit events, and policy authority.

## Registration

Nereus should register an Grotto executor per tenant with:

- name
- executor type such as `grotto`
- base URL
- stored manifest JSON
- stored capabilities JSON
- enabled flag

`sync-manifest` should call the Grotto worker, store the manifest/capabilities, and create a Nereus audit event.

## Routing

Nereus resolves:

```text
tenant_id + capability + task_type -> Executor
```

Disabled executors are ignored. Unknown capabilities fail cleanly. Multiple matching executors should be selected deterministically until richer department/user scoping exists.

## Policy

Nereus may use Grotto side-effect classes and policy hints as input, but Nereus makes the final policy decision:

- read-only tasks can run automatically
- tasks that mutate external systems require approval
- tasks that send external messages require approval
- tasks that touch secrets are rejected by default
- unknown task types require approval

Grotto should never be treated as an approval authority.

## Browser runtime split

`grotto-browser-agent` talks to separate browser runtime images. In the Nereus product path, those runtime images are packaged and published by `nereus-web`; the Grotto image Nereus normally deploys is the browser-agent worker, not an Grotto browser runtime. Nereus should keep browser-control endpoints private and internal-only. Grotto browser workers should return screenshots/traces/artifacts as evidence; Nereus decides what becomes durable audit.

For the concrete Nereus worker deployment and NetworkPolicy label contract, see [`nereus-browser-worker.md`](nereus-browser-worker.md).
