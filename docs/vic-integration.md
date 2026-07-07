
# VIC Integration

VIC can ingest OpenQuad workers as external task executors, but OpenQuad remains a generic worker family.

## Boundary

```text
VIC WorkflowRun
  -> VIC Task
  -> VIC policy evaluation
  -> OpenQuad worker task API
  -> OpenQuad structured result/artifacts/events
  -> VIC task status/audit/workflow continuation
```

VIC remains the control plane. It owns tenants, workflows, approvals, durable status, records, audit events, and policy authority.

## Registration

VIC should register an OpenQuad executor per tenant with:

- name
- executor type such as `openquad`
- base URL
- stored manifest JSON
- stored capabilities JSON
- enabled flag

`sync-manifest` should call the OpenQuad worker, store the manifest/capabilities, and create a VIC audit event.

## Routing

VIC resolves:

```text
tenant_id + capability + task_type -> Executor
```

Disabled executors are ignored. Unknown capabilities fail cleanly. Multiple matching executors should be selected deterministically until richer department/user scoping exists.

## Policy

VIC may use OpenQuad side-effect classes and policy hints as input, but VIC makes the final policy decision:

- read-only tasks can run automatically
- tasks that mutate external systems require approval
- tasks that send external messages require approval
- tasks that touch secrets are rejected by default
- unknown task types require approval

OpenQuad should never be treated as an approval authority.

## Browser runtime split

`openquad-browser-agent` talks to separate browser runtime images. In the VIC product path, those runtime images are packaged and published by `vic-web`; the OpenQuad image VIC normally deploys is the browser-agent worker, not an OpenQuad browser runtime. VIC should keep browser-control endpoints private and internal-only. OpenQuad browser workers should return screenshots/traces/artifacts as evidence; VIC decides what becomes durable audit.

For the concrete VIC worker deployment and NetworkPolicy label contract, see [`vic-browser-worker.md`](vic-browser-worker.md).
