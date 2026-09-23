# PlayNow Observer

`grotto-playnow-observer` is a passive evidence observer for an operator-owned PlayNow browser/session. It accepts only a loopback CDP endpoint, validates the current page against caller-approved origins, and consumes a caller-exported structured snapshot. It never navigates, clicks, stores passwords, bypasses geolocation or anti-bot controls, or places a wager.

Actual combined SGP prices are marked `SGP_PRICE_OBSERVED`; absent prices are explicitly `SGP_PRICE_NOT_OBSERVED`. No multiplication is treated as executable truth.

The first release deliberately leaves DOM extraction in the caller-owned browser bridge. Paths: `/work/input`, `/work/raw`, `/work/output`, `/work/logs`. Ports: none. Canary: `grotto-playnow-observer canary`.
