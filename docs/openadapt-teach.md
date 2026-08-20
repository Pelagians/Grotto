# Grotto OpenAdapt Teach worker

This image is a bounded integration adapter between a caller-owned browser and
upstream `openadapt-flow`. It is not a Nereus authority surface and does not
contain a Pelagian automation engine.

## Boundary

The adapter:

- accepts a Nereus-scoped, non-secret session configuration;
- requires a loopback CDP endpoint and `actuation_class: ui_only`;
- reuses the single existing browser context and page;
- installs upstream Flow recording instrumentation in the current document and
  on future navigations;
- delegates native recording and compilation to the pinned Flow release;
- leaves browser lifecycle with `web-apps`;
- emits bounded evidence rather than OpenAdapt procedure contents.

It does not authorize a session, store credentials, promote a learned revision,
issue a lease, replay a bundle, verify a business effect, call a connector, or
provide an MCP/tool surface.

## Runtime topology

Run this image as a sidecar in the same pod as a headful `web-apps`
BrowserRuntimeRelease. The browser must bind CDP to pod loopback. Selkies access
must remain behind Nereus-authenticated routing. Do not expose CDP through a
Service.

The expected writable directories are:

| Path | Contents | Lifetime |
| --- | --- | --- |
| `/work/source` | OpenAdapt-native recording directory | Ephemeral until uploaded |
| `/work/decisions` | Human decision input supplied by Nereus | Ephemeral, read-only where practical |
| `/work/bundle` | OpenAdapt-native compiled bundle | Ephemeral until uploaded |
| `/tmp/openadapt-home` | Library scratch state | Ephemeral |

The browser profile is not mounted into this container.

## Recording configuration

```json
{
  "teach_session_id": "opaque-session-id",
  "cdp_url": "http://127.0.0.1:9222",
  "start_url": "https://target.internal/task",
  "source_dir": "/work/source",
  "stop_file": "/work/stop",
  "ready_file": "/work/ready",
  "engine_release": {"release_id": "openadapt-flow-1.31.0"},
  "browser_runtime_release": {"release_id": "web-apps-browser-runtime"},
  "adapter_release": {"release_id": "grotto-openadapt-teach"},
  "actuation_class": "ui_only",
  "secret_fields": ["password"],
  "param_fields": ["report_date"],
  "identifier_fields": []
}
```

The adapter configuration must not contain browser credentials or Nereus
bearer credentials. Artifact upload credentials belong in a separate
short-lived delivery mechanism added by the deployment layer.

```sh
grotto-openadapt-teach record --config /work/attach.json
```

Nereus must not open the human interaction gate until the adapter creates the
configured readiness file. That file means the current document and future
navigations are instrumented and the initial settled frame exists. It does not
authorize the session or confer execution authority.

## Compilation

The human decision artifact accepted by this spike contains only:

```json
{
  "workflow_name": "Export legacy report",
  "param_overrides": {"step_001": "report_date"},
  "secret_param_steps": []
}
```

```sh
grotto-openadapt-teach compile \
  --source /work/source \
  --decisions /work/decisions/decisions.json \
  --bundle /work/bundle
```

Compilation disables model annotation and effect mining. A bounded structural
check rejects non-empty OpenAdapt API bindings or a declared non-UI actuator.
This is worker evidence, not Nereus qualification or admission.

## Security posture

- The image installs Flow core plus its exact Playwright browser dependency,
  not hosted or agent extras.
- The Flow 1.31.0 wheel is verified against SHA-256
  `81133db1528ad1bb1f26e3fcb6aea61b0651db6d905cf2e4943e8383c1f3d29c`;
  PyPI provenance binds that release to upstream commit
  `faf9945537d4011baeb36ce5f063b6e1814903e6`.
- It contains no browser binary and cannot silently launch a replacement
  browser; browser auto-install is disabled.
- Model and cloud endpoints/tokens are explicitly empty.
- Infrastructure must still deny public egress.
- Source frames, DOM/accessibility text, OCR products and bundle templates are
  governed sensitive artifacts.
- Password/declared-secret exclusion remains an attestation, not proof that
  arbitrary opaque bytes contain no credentials.
- Generated `workflow.py` is opaque artifact content and must never be imported
  or executed by Pelagian.

## Current spike limitation

Flow does not yet publish caller-owned interactive-recorder attachment as a
first-class API. This adapter reuses the upstream recorder pump but touches its
private initialization constants and state. If the live compatibility spike
passes, the maintenance follow-up should be a small upstream
`page=..., owns_browser=false` API rather than a fork.
