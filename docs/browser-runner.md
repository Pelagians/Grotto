# browser.screenshot Runner

The Phase 1 `browser.screenshot` runner lives in `workerd/openquad_workerd/runners_browser.py`.

## Quick reference

| Item | Value |
|------|-------|
| File | `workerd/openquad_workerd/runners_browser.py` |
| Dispatch | `runners.py` → `browser.screenshot` / `screenshot` |
| Env | `BROWSER_WS_ENDPOINT` (Playwright WS) or `BROWSER_CDP_ENDPOINT` (raw CDP) |
| Input | `url` (required), `viewport` (optional), `full_page` (optional) |
| Constraint | `allowed_domains` — domain allowlisting |
| Artifact | `screenshot.png` (png, image/png) with sha256 + size_bytes |
| Events | `task.tool_start`, `task.tool_done`, `task.tool_error`, `task.artifact_written` |
| Smoke | `scripts/smoke_browser_container.sh` (container-level verification) |

## Runner lifecycle

1. Validate `url` (scheme, hostname)
2. Check `allowed_domains` constraint
3. Require `BROWSER_WS_ENDPOINT` or `BROWSER_CDP_ENDPOINT`
4. Prepare task directory
5. Call `_execute_screenshot()` with Playwright
6. Write PNG artifact + manifest
7. Record events
8. Return `TaskResult`

## Connection modes

- **BROWSER_WS_ENDPOINT** → `playwright.chromium.connect(ws_endpoint)` (Playwright remote browser protocol)
- **BROWSER_CDP_ENDPOINT** → `playwright.chromium.connect_over_cdp(cdp_endpoint)` (Chrome DevTools Protocol)

## Next for OpenQuad

1. **Deploy smoke** — run `smoke_browser_container.sh` with a real container engine to verify the browser-agent image builds and the runner dispatches correctly
2. **Runtime integration** — wire the runner to a running `vic-web` or `openquad-browser-runtime-headless` instance for a real Playwright screenshot
3. **Error detail** — improve navigation timeout handling, network errors, domain mismatch detail in result
4. **Viewport control** — clamp viewport at the runner level (max width/height) and surface constraint violations
5. **Docs** — this file should expand with deployment and integration examples
