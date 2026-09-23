#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from worker_common import artifact, bounded_get, finish_bundle, read_job, utc_now

RELEASE = os.environ.get("GROTTO_BUILD_REVISION", "grotto-sports-market-probe-dev")


def _payload(job: dict[str, Any]) -> tuple[bytes, str, str]:
    fixture = job.get("fixture_path")
    if fixture:
        raw = Path(str(fixture)).read_bytes()
        return raw, "application/json", f"file://{fixture}"
    endpoints = job.get("endpoints", [])
    if not isinstance(endpoints, list) or len(endpoints) != 1:
        raise ValueError("market probe requires exactly one bounded endpoint")
    if int(job.get("max_requests", 0)) < 1:
        raise ValueError("max_requests must permit the single request")
    url = str(endpoints[0])
    raw, media = bounded_get(
        url,
        allowed_hosts=set(map(str, job.get("allowed_hosts", []))),
        timeout=min(float(job.get("deadline_seconds", 60)), 60.0),
        max_bytes=min(int(job.get("max_bytes", 5_000_000)), 10_000_000),
        credential_env=str(job["credential_env"])
        if job.get("credential_env")
        else None,
        credential_query_param=(
            str(job["credential_query_param"])
            if job.get("credential_query_param")
            else None
        ),
    )
    return raw, media, url


def _extract(
    job: dict[str, Any], raw: bytes, observed_at: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(raw)
    games = data if isinstance(data, list) else [data]
    availability: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []
    wanted = set(map(str, job.get("requested_market_keys", [])))
    for game in games:
        if not isinstance(game, dict):
            continue
        provider_event_id = str(game.get("id", ""))
        if (
            job.get("provider_event_id")
            and provider_event_id != job["provider_event_id"]
        ):
            continue
        for bookmaker in game.get("bookmakers", []):
            book = str(bookmaker.get("key", ""))
            for market in bookmaker.get("markets", []):
                key = str(market.get("key", ""))
                if wanted and key not in wanted:
                    continue
                availability.append(
                    {
                        "event_id": job["event_id"],
                        "provider_event_id": provider_event_id,
                        "book": book,
                        "market_key": key,
                        "first_seen_at": observed_at,
                        "last_seen_at": observed_at,
                        "status": "OPEN",
                        "raw_evidence_id": "raw-0",
                    }
                )
                for outcome in market.get("outcomes", []):
                    quotes.append(
                        {
                            "event_id": job["event_id"],
                            "provider_event_id": provider_event_id,
                            "provider_player_id": outcome.get("participant_id"),
                            "player_name": outcome.get("description"),
                            "market_key": key,
                            "selection": outcome.get("name"),
                            "line": outcome.get("point"),
                            "price": outcome.get("price"),
                            "book": book,
                            "status": "ACTIVE"
                            if not outcome.get("suspended")
                            else "SUSPENDED",
                            "observed_at": observed_at,
                            "provider_timestamp": market.get("last_update")
                            or bookmaker.get("last_update"),
                            "raw_evidence_id": "raw-0",
                        }
                    )
    return availability, quotes


def run(input_path: str, output_path: str) -> None:
    job = read_job(input_path)
    observed_at = utc_now()
    raw, media_type, source_url = _payload(job)
    availability, quotes = _extract(job, raw, observed_at)
    finish_bundle(
        {
            "job_id": job["job_id"],
            "event_id": job["event_id"],
            "observed_at": observed_at,
            "provider": job["provider"],
            "worker_release": RELEASE,
            "market_availability": availability,
            "quotes": quotes,
            "raw_artifacts": [
                artifact(
                    raw,
                    artifact_id="raw-0",
                    source_url=source_url,
                    media_type=media_type,
                )
            ],
        },
        output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded sportsbook evidence collector"
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
                    "worker": "grotto-sports-market-probe",
                    "release": RELEASE,
                    "status": "ok",
                }
            )
        )
    else:
        run(args.input, args.output)


if __name__ == "__main__":
    main()
