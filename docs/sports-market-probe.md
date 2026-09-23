# Sports Market Probe

`grotto-sports-market-probe` is an ephemeral, read-only sportsbook evidence collector. The caller supplies one approved HTTPS endpoint, explicit egress hosts, an event, market keys, deadline, byte ceiling, and request budget. A credential may be named by environment variable; its value is never accepted in the job or output.

The worker discovers provider market keys, emits quotes and raw content with per-artifact hashes, and exits. It does not resolve canonical player identity, qualify positions, schedule itself, or write Sports Edge Lab state.

Paths: `/work/input`, `/work/raw`, `/work/output`, `/work/logs`. Ports: none. Canary: `grotto-sports-market-probe canary`.
