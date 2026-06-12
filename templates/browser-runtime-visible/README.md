# openquad-browser-runtime-visible

Browser runtime only. No OpenClaw model, no reasoning agent, and no Homebrew appliance layer.

This image runs visible Chromium under Xvfb with VNC/noVNC support and a Chromium CDP endpoint. It is intended for login, teaching, debugging, and user-assisted workflows, with a persistent browser profile volume.

Treat CDP, VNC, and noVNC as privileged browser-control access. Do not expose them publicly.
