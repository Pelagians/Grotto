# Sports Market Probe

`grotto-sports-market-probe` is an ephemeral, read-only sportsbook evidence collector. The caller supplies bounded approved HTTPS endpoints, explicit egress hosts, an event, market keys, deadline, byte ceiling, and request budget. A credential may be named by environment variable; its value is never accepted in the job or output.

Operations are explicit: `HEADLINE`, `EVENT_INDEX`, `EVENT_DISCOVERY`, or `EVENT_QUOTES`. The event index emits the provider event IDs needed for deterministic event matching. Market discovery emits availability separately from quote retrieval. Quotes are filtered to explicit caller keys. Each bundle includes per-book/provider capability reasons, request success/failure counts, and quota headers where returned. HTTP failures are sanitized so credentialed URLs cannot enter output or logs.

The worker emits market availability, quotes, provider timestamps where present, actual retrieval time, worker job/release, and raw content with per-artifact hashes, then exits. It does not resolve canonical player identity, qualify positions, schedule itself, or write Sports Edge Lab state.

Paths: `/work/input`, `/work/raw`, `/work/output`, `/work/logs`. Ports: none. Canary: `grotto-sports-market-probe canary`.
