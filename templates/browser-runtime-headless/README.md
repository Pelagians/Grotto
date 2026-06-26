# openquad-browser-runtime-headless

Browser runtime only. No OpenClaw model, no reasoning agent, and no Homebrew appliance layer.

This image runs a Playwright Chromium browser server and exposes an internal Playwright WebSocket endpoint, defaulting to port `3000`. Treat that endpoint as privileged browser-control access.

Use for repeatable headless workflows. Do not expose this service publicly.

The launcher accepts browser-family-agnostic aliases for downstream runtime images: `BROWSER_WS_HOST`, `BROWSER_WS_PORT`, `BROWSER_HEADLESS`, `BROWSER_EXTRA_ARGS`, `BROWSER_EXECUTABLE_PATH`, and `PLAYWRIGHT_BROWSER_CHANNEL`. Legacy `PLAYWRIGHT_*` and `CHROMIUM_ARGS` names remain supported.
