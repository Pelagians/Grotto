# PlayNow Observer

`grotto-playnow-observer` is a passive evidence observer for an operator-owned PlayNow browser/session. It accepts only a loopback CDP endpoint, selects a page whose origin is explicitly caller-approved, and consumes a caller-exported structured snapshot. It never navigates, clicks, stores passwords or cookies, bypasses geolocation or anti-bot controls, or places a wager. Query strings and fragments are rejected so session material cannot enter evidence.

Each market must carry canonical event/market/subject fields, selection, period, actual observation time, and one of `OBSERVED`, `NOT_FOUND`, `SUSPENDED`, `REMOVED`, or `UNRESOLVED`. The caller supplies an opaque browser-session ID; the bundle preserves it together with worker job/release and the bundle digest. Authenticated HTML and browser profiles are never accepted as artifacts.

Actual combined SGP prices are marked `SGP_PRICE_OBSERVED`; absent prices are explicitly `SGP_PRICE_NOT_OBSERVED`. No multiplication is treated as executable truth.

The first release deliberately leaves DOM extraction in the caller-owned browser bridge. Paths: `/work/input`, `/work/raw`, `/work/output`, `/work/logs`. Ports: none. Canary: `grotto-playnow-observer canary`.
