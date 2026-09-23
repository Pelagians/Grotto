# PlayNow Observer

`grotto-playnow-observer` is a passive evidence observer for an operator-owned PlayNow browser/session. It accepts only a loopback CDP endpoint, requires the exact caller-requested PlayNow page to be open, and consumes a caller-exported structured snapshot. It never navigates, clicks, stores passwords or cookies, bypasses geolocation or anti-bot controls, or places a wager. Query strings and fragments are rejected so session material cannot enter evidence.

Each market must carry canonical event/market/subject fields, selection, period, actual observation time, and one of `OBSERVED`, `NOT_FOUND`, `SUSPENDED`, `REMOVED`, or `UNRESOLVED`. The caller supplies an opaque browser-session ID; the bundle preserves it together with worker job/release and the bundle digest. Authenticated HTML and browser profiles are never accepted as artifacts.

Actual combined SGP prices are marked `SGP_PRICE_OBSERVED`; absent prices are explicitly `SGP_PRICE_NOT_OBSERVED`. No multiplication is treated as executable truth.

The first release deliberately leaves DOM extraction in the caller-owned browser bridge. Paths: `/work/input`, `/work/raw`, `/work/output`, `/work/logs`. Ports: none. Canary: `grotto-playnow-observer canary`.

## Operator launch and attachment

The operator, not the worker, starts and owns the browser. On Windows, close any previous dedicated PlayNow window, then run the following in PowerShell. This profile remains on the operator's machine and must never be mounted into the worker or copied into evidence.

```powershell
$playnowProfile = Join-Path $env:LOCALAPPDATA "SportsEdgeLab\PlayNowOperator"
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
& $edge --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$playnowProfile" "https://www.playnow.com/sports"
```

In that dedicated window, the operator manually signs in if required, confirms the site is showing the correct British Columbia offering, opens the selected NFL event, and leaves the window running. The worker never enters credentials, changes location, adjusts account settings, handles funds, sets stakes, or submits wagers.

For a bounded local research capture, `scripts/playnow_cdp_capture.mjs` is the caller-side
bridge. It accepts one exact PlayNow event URL and an ignored output path, waits for the
event market surface, and visits only the named market-category tabs. It extracts only
the market containers inside the page's `main` region. It does not access cookies,
storage, the account header, browser profiles, or unrelated tabs, and it never clicks
an odds selection or bet-slip control. The resulting raw bridge artifact is not a
Grotto bundle; the observer must still validate the live attachment and emit the hashed
evidence bundle.

The caller-owned bridge exports only the normalized market snapshot to a local ignored exchange path. The live job identifies the opaque session, limits attachment to loopback, and permits only the exact PlayNow origin:

```json
{
  "session_mode": "caller_owned",
  "browser_session_id": "operator-assigned-ephemeral-id",
  "session_authenticated": true,
  "cdp_url": "http://127.0.0.1:9222",
  "page_url": "https://www.playnow.com/sports",
  "allowed_origins": ["https://www.playnow.com"],
  "attach_wait_seconds": 30,
  "attach_poll_seconds": 1
}
```

`attach_wait_seconds` enables a bounded, passive reattachment window of at most 300 seconds. It retries only when the local endpoint or approved page is temporarily unavailable; policy, authentication, origin, and runtime failures fail immediately.

Stable diagnostic reasons are:

- `BROWSER_NOT_RUNNING`: the required caller-owned session identity was not supplied.
- `ATTACH_ENDPOINT_UNAVAILABLE`: the loopback debugging endpoint could not be reached.
- `SESSION_UNAUTHENTICATED`: the caller explicitly reported that the session is not authenticated.
- `PLAYNOW_ORIGIN_NOT_OPEN`: attachment succeeded but no approved PlayNow page was open.
- `ORIGIN_NOT_ALLOWED`: the supplied or attached page is outside the allowlist, uses a non-HTTPS origin, or contains query/fragment material.
- `ATTACHMENT_FAILED`: the endpoint answered but did not provide a usable browser-page inventory.
- `BROWSER_RUNTIME_UNSUPPORTED`: the endpoint is not loopback HTTP.
