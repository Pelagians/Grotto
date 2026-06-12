# openquad-browser-runtime-headless

Browser runtime only. No OpenClaw model, no reasoning agent, and no Homebrew appliance layer.

This image runs a Playwright Chromium browser server and exposes an internal Playwright WebSocket endpoint, defaulting to port `3000`. Treat that endpoint as privileged browser-control access.

Use for repeatable headless workflows. Do not expose this service publicly.
