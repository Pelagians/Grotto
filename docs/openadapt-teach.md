# Grotto OpenAdapt Teach worker

This image is a bounded integration adapter between a caller-owned browser and
upstream `openadapt-flow`. It is not a Nereus authority surface and does not
contain a Pelagian automation engine.

**Research spike.** The seam it proves is not yet a production runtime contract.
See "Upstream dependency" below for the condition that must clear first.

## Boundary

The adapter:

- accepts a Nereus-scoped, non-secret session configuration;
- requires a loopback CDP endpoint and `actuation_class: ui_only`;
- reuses the single existing browser context;
- installs upstream Flow recording instrumentation at **browser-context** scope,
  covering the current documents, future navigations, and pages created after
  recording begins;
- delegates native recording and compilation to the pinned Flow release;
- leaves browser lifecycle with `web-apps`;
- emits bounded evidence rather than OpenAdapt procedure contents.

It does not authorize a session, store credentials, promote a learned revision,
issue a lease, replay a bundle, verify a business effect, call a connector, or
provide an MCP/tool surface.

## Passive recording is enforced, not promised

Loopback CDP is **exposure containment, not an authorization boundary**. Any
process that reaches the endpoint holds full browser-session authority: it can
navigate, read every origin the profile is logged into, and exfiltrate cookies.
Sharing a network namespace with the browser removes the network barrier
entirely, so the restraint has to live somewhere it can be checked.

Three things carry it:

1. **The adapter never drives the browser.** It makes no `goto`, `click`,
   `fill`, `reload`, `route`, or `add_cookies` call. `tests/test_openadapt_teach_policy.py`
   walks the module's AST and fails if any driving call appears, so a future
   edit cannot quietly reintroduce navigation authority.
2. **Origins are server-supplied.** `allowed_origins` is required. At attach the
   adapter asserts every existing page is already inside it and refuses
   otherwise; it cannot navigate somewhere authorized, only decline. Pages that
   appear later outside the allowlist are left alone and logged as
   uninstrumented.
3. **The browser is disposable.** Real containment comes from the ephemeral
   `web-apps` Teach browser profile, not from this adapter. See
   `web-apps/docs/openadapt-teach-spike.md`.

A JSON scan of the compiled bundle is not a substitute for any of this, and is
not treated as one.

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
  "allowed_origins": ["https://target.internal"],
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
configured readiness file. That file means the existing documents and future
navigations are instrumented and the initial settled frame exists. It does not
authorize the session or confer execution authority.

`start_url` is logged as a SHA-256 digest, never verbatim: a target URL
routinely carries record identifiers or a session token.

## Page and popup coverage

Instrumentation is installed on the `BrowserContext`, not on one `Page`:

- `context.add_init_script` covers future documents in every page, including
  child frames as they attach;
- `context.expose_binding` gives every page in the context, including popups,
  a route into the same recorder queue;
- `context.on("page")` instruments pages created after recording begins;
- at attach, every already-loaded frame of every existing page is injected
  directly, because an init script by definition cannot reach a document that
  already exists.

**Known gap.** Flow's `Recorder` binds screenshots and settle detection to a
single primary page. Popup *events* are recorded through the shared context
binding; popup *frames* are not captured. This is an upstream limitation, not
something to work around locally, and it is one of the reasons the seam is
still a spike.

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
check rejects non-empty OpenAdapt API bindings or a declared non-UI actuator,
and refuses a bundle whose `schema_version` this adapter has not been read
against, because the check keys on field names a new schema may have renamed.
This is worker evidence, not Nereus qualification or admission.

## Artifact handling

`archive` streams in both directions and never holds an artifact in memory:

```sh
grotto-openadapt-teach archive \
  --source /work/source \
  --output /work/source.zip \
  --max-bytes 8589934592
```

The size ceiling is enforced while writing, not after. The reported digest is
worker evidence; Nereus recomputes it on receipt and treats its own value as
the artifact identity.

## Upstream dependency

Flow 1.31 does not publish a caller-owned attach lifecycle, so this adapter
composes around private `InteractiveRecorder` state.

Every private symbol is confined to `runtimes/openadapt-teach/openadapt_compat.py`.
No other module may import an OpenAdapt private name;
`tests/test_openadapt_teach_policy.py` enforces that, and also fails if the
compat module touches a private attribute it has not declared in its inventory.

**The canary.** `grotto-openadapt-teach canary` inventories the installed
release and exits non-zero if any declared private symbol, placeholder token,
or the `__oaflow_emit` binding name has moved. It runs at image build time, so
an upstream rename becomes a build failure rather than what it would otherwise
be: a recording that completes successfully with an empty event stream.

**The ask.** The seam should be replaced by a small upstream API:

```python
InteractiveRecorder(
    start_url,
    out_dir,
    *,
    context=caller_owned_browser_context,   # context, not page
    owns_browser=False,                     # finish() must never close it
    on_ready=callable,                      # instrumentation + first settled frame
    stop_when=callable,
)
```

`context=` rather than `page=` is deliberate: popups are context-level, so a
page-scoped attach API would bake in exactly the coverage gap described above.
`probe()` already detects this signature and reports `strategy: upstream`, so
the private seam retires itself the day upstream ships.

Do not fork Flow, and do not grow a parallel Pelagian recorder.

## Security posture

- The image installs Flow core plus its exact Playwright browser dependency,
  not hosted or agent extras.
- The base image is pinned by digest and every direct and transitive Python
  distribution is pinned by version and SHA-256 in
  `runtimes/openadapt-teach/requirements.lock.txt`, installed with
  `--require-hashes --no-deps` so pip resolves nothing at build time.
- PyPI provenance binds the Flow 1.31.0 release to upstream commit
  `faf9945537d4011baeb36ce5f063b6e1814903e6`.
- It contains no browser binary and cannot silently launch a replacement
  browser; browser auto-install is disabled, and the compat seam refuses to
  proceed if Flow's constructor ever stops being lazy.
- Model and cloud endpoints/tokens are explicitly empty.
- Infrastructure must still deny public egress.
- Source frames, DOM/accessibility text, OCR products and bundle templates are
  governed sensitive artifacts.
- Password/declared-secret exclusion remains an attestation, not proof that
  arbitrary opaque bytes contain no credentials. A grep for a known string
  cannot see a secret rendered into screenshot pixels.
- Generated `workflow.py` is opaque artifact content and must never be imported
  or executed by Pelagian.
