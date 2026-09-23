#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sports-workers"))

from worker_common import artifact, finish_bundle, read_job, utc_now

RELEASE = os.environ.get("GROTTO_BUILD_REVISION", "grotto-playnow-observer-dev")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
STATUSES = {"OBSERVED", "NOT_FOUND", "SUSPENDED", "REMOVED", "UNRESOLVED"}
REQUIRED_MARKET_FIELDS = {
    "event_id",
    "market_family",
    "market_key",
    "selection",
    "period",
    "status",
    "observed_at",
}
REATTACHABLE_FAILURES = {
    "ATTACH_ENDPOINT_UNAVAILABLE",
    "BROWSER_NOT_RUNNING",
    "PLAYNOW_ORIGIN_NOT_OPEN",
}


class ObserverFailure(ValueError):
    """Stable, machine-readable failure at the passive observation boundary."""


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_playnow_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "playnow.com" or host.endswith(".playnow.com"))


def _validate_page_url(page_url: str, allowed: set[str]) -> str:
    parsed = urlparse(page_url)
    origin = _origin(page_url)
    if not _is_playnow_origin(origin) or origin not in allowed:
        raise ObserverFailure("ORIGIN_NOT_ALLOWED")
    if parsed.query or parsed.fragment:
        raise ObserverFailure("ORIGIN_NOT_ALLOWED")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _page_matches(item: dict[str, Any], allowed: set[str], requested_page: str) -> bool:
    if item.get("type") != "page":
        return False
    url = str(item.get("url", ""))
    if _origin(url) not in allowed:
        return False
    try:
        page_url = _validate_page_url(url, allowed)
    except ObserverFailure:
        return False
    return not requested_page or page_url == requested_page


def _verify_browser(job: dict[str, Any]) -> str:
    cdp_url = str(job.get("cdp_url", ""))
    parsed = urlparse(cdp_url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK:
        raise ObserverFailure("BROWSER_RUNTIME_UNSUPPORTED")
    try:
        with urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=5) as response:
            pages = json.load(response)
    except HTTPError as error:
        raise ObserverFailure("ATTACHMENT_FAILED") from error
    except (OSError, TimeoutError, URLError) as error:
        raise ObserverFailure("ATTACH_ENDPOINT_UNAVAILABLE") from error
    except (json.JSONDecodeError, TypeError) as error:
        raise ObserverFailure("ATTACHMENT_FAILED") from error
    if not isinstance(pages, list):
        raise ObserverFailure("ATTACHMENT_FAILED")
    allowed = set(map(str, job.get("allowed_origins", [])))
    requested_page = str(job.get("page_url", ""))
    requested_page = (
        _validate_page_url(requested_page, allowed) if requested_page else ""
    )
    page = next(
        (
            item
            for item in pages
            if _page_matches(item, allowed, requested_page)
        ),
        None,
    )
    if not page:
        raise ObserverFailure("PLAYNOW_ORIGIN_NOT_OPEN")
    url = str(page.get("url", ""))
    return _validate_page_url(url, allowed)


def _verify_browser_with_wait(job: dict[str, Any]) -> str:
    wait_seconds = min(max(float(job.get("attach_wait_seconds", 0)), 0), 300)
    poll_seconds = min(max(float(job.get("attach_poll_seconds", 1)), 0.5), 10)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return _verify_browser(job)
        except ObserverFailure as error:
            if str(error) not in REATTACHABLE_FAILURES or time.monotonic() >= deadline:
                raise
            time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))


def _market(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    if "status" not in normalized and "state" in normalized:
        normalized["status"] = normalized.pop("state")
    missing = REQUIRED_MARKET_FIELDS - normalized.keys()
    if missing:
        raise ValueError(f"PlayNow observation missing fields: {','.join(sorted(missing))}")
    if normalized["status"] not in STATUSES:
        raise ValueError("unsupported PlayNow observation status")
    if normalized["status"] == "OBSERVED" and normalized.get("price") is None:
        raise ValueError("observed PlayNow price is required")
    normalized["raw_evidence_id"] = "raw-0"
    return normalized


def run(input_path: str, output_path: str) -> None:
    job = read_job(input_path)
    if job.get("session_mode") != "caller_owned" or not job.get("browser_session_id"):
        raise ObserverFailure("BROWSER_NOT_RUNNING")
    if job.get("session_authenticated") is False:
        raise ObserverFailure("SESSION_UNAUTHENTICATED")
    page_url = (
        _verify_browser_with_wait(job)
        if job.get("cdp_url")
        else str(job.get("page_url", ""))
    )
    allowed = set(map(str, job.get("allowed_origins", [])))
    page_url = _validate_page_url(page_url, allowed)
    snapshot_path = Path(str(job["snapshot_path"]))
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    markets = [_market(item) for item in snapshot.get("markets", [])]
    sgp = []
    for item in snapshot.get("sgp_observations", []):
        if item.get("price") is None:
            sgp.append({**item, "status": "SGP_PRICE_NOT_OBSERVED"})
        else:
            sgp.append({**item, "status": "SGP_PRICE_OBSERVED"})
    finish_bundle(
        {
            "job_id": job["job_id"],
            "event_id": job["event_id"],
            "observed_at": utc_now(),
            "book": "playnow",
            "markets": markets,
            "sgp_observations": sgp,
            "session_mode": "caller_owned",
            "browser_session_id": job["browser_session_id"],
            "worker_release": RELEASE,
            "page_url": page_url,
            "raw_artifacts": [
                artifact(
                    raw,
                    artifact_id="raw-0",
                    source_url=page_url,
                    media_type="application/json",
                )
            ],
        },
        output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Passive caller-owned PlayNow evidence observer"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("canary")
    command = sub.add_parser("run")
    command.add_argument("--input", required=True)
    command.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "canary":
        print(
            json.dumps(
                {
                    "worker": "grotto-playnow-observer",
                    "release": RELEASE,
                    "status": "ok",
                }
            )
        )
    else:
        try:
            run(args.input, args.output)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(
                json.dumps(
                    {
                        "worker": "grotto-playnow-observer",
                        "status": "failed",
                        "reason": str(error),
                    }
                ),
                file=sys.stderr,
            )
            raise SystemExit(2) from None


if __name__ == "__main__":
    main()
