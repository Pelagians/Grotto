# grotto-browser-agent

Browser-workflow OpenClaw agent for sites and legacy portals where APIs do not exist. This image contains agent logic, model config, policy, and Playwright client tooling only. It does not bundle headless/headful browser stacks.

## Runtime connection model

Prefer Playwright-native WebSocket control of `grotto-browser-runtime-headless`. Use Chromium CDP against `grotto-browser-runtime-visible` for persistent-profile, teaching, debugging, and user-assisted workflows.

Browser-control endpoints are privileged and must stay internal to the cluster or trusted Podman network. In Kubernetes, expose them only through Sernereuse DNS and restrict them with NetworkPolicy.

## Mutation model

Safe autonomous actions: navigate, read, allowed-site search, extract, download, managed uploads, and form filling. Submitting low-risk forms requires explicit workflow policy. Payments, purchases, security/account settings, destructive admin actions, high-risk submissions, mass scraping, captcha-solving, and credential harvesting are blocked or confirmation-gated.

## Expected output contract

Results should include `workflow`, `target`, `actions`, `artifacts`, `policy_decision`, `evidence`, and `provenance`.
