#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from worker_common import artifact, finish_bundle, read_job, utc_now

RELEASE = os.environ.get("GROTTO_BUILD_REVISION", "grotto-playnow-observer-dev")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _verify_browser(job: dict[str, Any]) -> str:
    cdp_url = str(job.get("cdp_url", ""))
    parsed = urlparse(cdp_url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK:
        raise ValueError("caller-owned browser CDP endpoint must be loopback HTTP")
    with urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=5) as response:
        pages = json.load(response)
    allowed = set(map(str, job.get("allowed_origins", [])))
    page = next((item for item in pages if item.get("type") == "page"), None)
    if not page:
        raise ValueError("caller-owned browser has no observable page")
    url = str(page.get("url", ""))
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if origin not in allowed:
        raise ValueError("browser page is outside allowed PlayNow origins")
    return url


def run(input_path: str, output_path: str) -> None:
    job = read_job(input_path)
    page_url = (
        _verify_browser(job) if job.get("cdp_url") else str(job.get("page_url", ""))
    )
    allowed = set(map(str, job.get("allowed_origins", [])))
    parsed = urlparse(page_url)
    if f"{parsed.scheme}://{parsed.netloc}" not in allowed:
        raise ValueError("snapshot origin is outside allowed PlayNow origins")
    snapshot_path = Path(str(job["snapshot_path"]))
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    markets: list[dict[str, Any]] = []
    for item in snapshot.get("markets", []):
        state = str(item.get("state", "UNRESOLVED"))
        if state not in {
            "OBSERVED",
            "NOT_FOUND",
            "SUSPENDED",
            "UNAVAILABLE",
            "UNRESOLVED",
        }:
            raise ValueError("unsupported PlayNow observation state")
        markets.append({**item, "raw_evidence_id": "raw-0"})
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
        run(args.input, args.output)


if __name__ == "__main__":
    main()
