# Browser Runtime Contract

OpenQuad browser runtime images expose browser-control endpoints for narrow workers and orchestrators. They are runtime surfaces, not agents and not policy authorities.

This contract is intentionally browser-family agnostic so closed or downstream images can provide branded browsers such as Chrome, Edge, or Brave without forking OpenQuad's worker/control-plane assumptions.

## Runtime roles

- `openquad-browser-runtime-headless` exposes a Playwright WebSocket endpoint for repeatable automated workflows.
- `openquad-browser-runtime-visible` exposes browser CDP plus VNC/noVNC for login, teaching, debugging, and user-assisted workflows.
- `openquad-browser-agent` or a trusted orchestrator connects to these endpoints over internal networking.

Browser-control endpoints are privileged. Do not expose Playwright WS, CDP, VNC, or noVNC publicly.

## Headless runtime

Default endpoint:

| Env | Legacy alias | Default | Purpose |
| --- | --- | --- | --- |
| `BROWSER_WS_HOST` | `PLAYWRIGHT_WS_HOST` | `0.0.0.0` | Playwright WebSocket bind host |
| `BROWSER_WS_PORT` | `PLAYWRIGHT_WS_PORT` | `3000` | Playwright WebSocket port |
| `BROWSER_HEADLESS` | `PLAYWRIGHT_HEADLESS` | `true` | Whether Playwright launches headless |
| `BROWSER_DOWNLOAD_DIR` | — | `/home/pwuser/downloads` | Download path |
| `BROWSER_ARTIFACTS_DIR` | — | `/home/pwuser/artifacts` | Artifact path |
| `BROWSER_EXTRA_ARGS` | `CHROMIUM_ARGS` | empty | Extra browser flags appended after legacy flags |
| `BROWSER_EXECUTABLE_PATH` | `CHROMIUM_BIN` | empty | Explicit browser executable path; takes precedence over channel |
| `PLAYWRIGHT_BROWSER_CHANNEL` | `BROWSER_CHANNEL` | empty | Playwright channel, e.g. `chrome` or `msedge` |

The OpenQuad image still defaults to Playwright's bundled Chromium. Downstream images can provide `PLAYWRIGHT_BROWSER_CHANNEL=chrome` / `msedge`, or `BROWSER_EXECUTABLE_PATH=/usr/bin/brave-browser`, without changing the OpenQuad headless launcher.

## Visible runtime

Default endpoints:

| Env | Legacy alias | Default | Purpose |
| --- | --- | --- | --- |
| `BROWSER_CDP_HOST` | `CHROMIUM_CDP_HOST` | `0.0.0.0` | CDP bind host |
| `BROWSER_CDP_PORT` | `CHROMIUM_CDP_PORT` | `9222` | CDP port |
| `BROWSER_EXECUTABLE_PATH` | `CHROMIUM_BIN` | Playwright Chromium path | Browser binary to launch |
| `BROWSER_EXTRA_ARGS` | `CHROMIUM_EXTRA_ARGS` | empty | Extra browser flags appended after legacy flags |
| `BROWSER_START_URL` | `CHROMIUM_START_URL` | `about:blank` | Initial URL |
| `BROWSER_POLICY_DIR` | `CHROMIUM_POLICY_DIR` | `/etc/chromium/policies/managed` | Managed policy mount path |
| `BROWSER_REMOTE_ALLOW_ORIGINS` | `CHROMIUM_REMOTE_ALLOW_ORIGINS` | empty | Optional CDP remote-origin flag value |
| `BROWSER_PROFILE_DIR` | — | `/home/pwuser/browser-profile` | Browser profile path |
| `BROWSER_DOWNLOAD_DIR` | — | `/home/pwuser/downloads` | Download path |
| `VISIBLE_BROWSER_MODE` | — | `locked` | `locked` browser-only mode or `desktop` debug mode |

The visible runtime directly launches the selected browser executable under Xvfb. Downstream images should set `BROWSER_EXECUTABLE_PATH` for branded browsers.

## Readiness output

Both runtimes print a JSON readiness record to stdout. Callers should treat it as informational; Kubernetes readiness should still use endpoint probes appropriate to the deployment.

Headless readiness includes:

```json
{
  "status": "ready",
  "runtime": "browser-runtime-headless",
  "endpoint": "ws://...",
  "browserLaunchOptions": {}
}
```

Visible readiness includes:

```json
{
  "status": "ready",
  "runtime": "browser-runtime-visible",
  "mode": "locked",
  "browserExecutable": "/path/to/browser",
  "cdp": "http://0.0.0.0:9222",
  "vnc": "5900",
  "novnc": "6080"
}
```

## Validation

Run the dependency-light runtime contract tests with:

```bash
make test-browser-runtime
```

These tests do not launch a real browser or container engine. They verify the launcher option resolver, visible-runtime env alias contract, and headless image packaging layout. A real image build and browser launch remains required before publishing runtime images.
