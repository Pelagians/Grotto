#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sports-workers"))

from worker_common import (
    BoundedHttpError,
    artifact,
    bounded_get,
    finish_bundle,
    read_job,
    utc_now,
)

RELEASE = os.environ.get("GROTTO_BUILD_REVISION", "grotto-sports-market-probe-dev")
OPERATIONS = {"HEADLINE", "EVENT_INDEX", "EVENT_DISCOVERY", "EVENT_QUOTES"}
PLAN_UNSUPPORTED_CODES = {"OUT_OF_USAGE_CREDITS", "UNAUTHORIZED", "INVALID_KEY"}


def _quota(headers: dict[str, str]) -> dict[str, int | None]:
    def value(name: str) -> int | None:
        try:
            return int(headers[name])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "used": value("x-requests-used"),
        "remaining": value("x-requests-remaining"),
        "last_cost": value("x-requests-last"),
    }


def _capability(
    job: dict[str, Any],
    *,
    book: str | None,
    market_key: str,
    status: str,
    reason: str,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "provider": job["provider"],
        "provider_event_id": job.get("provider_event_id"),
        "book": book,
        "market_key": market_key,
        "status": status,
        "reason": reason,
        "observed_at": observed_at,
        "worker_job_id": job["job_id"],
        "worker_release": RELEASE,
    }


def _discovery(
    job: dict[str, Any], data: Any, observed_at: str, artifact_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    game = data if isinstance(data, dict) else {}
    provider_event_id = str(game.get("id") or job.get("provider_event_id") or "")
    requested = set(map(str, job.get("requested_market_keys", [])))
    availability: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    observed_pairs: set[tuple[str, str]] = set()
    books: set[str] = set()
    for bookmaker in game.get("bookmakers", []):
        if not isinstance(bookmaker, dict):
            continue
        book = str(bookmaker.get("key", ""))
        books.add(book)
        for market in bookmaker.get("markets", []):
            key = str(market.get("key", ""))
            if not key or (requested and key not in requested):
                continue
            observed_pairs.add((book, key))
            availability.append(
                {
                    "event_id": job["event_id"],
                    "provider": job["provider"],
                    "provider_event_id": provider_event_id,
                    "book": book,
                    "market_key": key,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                    "status": "AVAILABLE",
                    "provider_timestamp": bookmaker.get("last_update"),
                    "raw_evidence_id": artifact_id,
                    "worker_job_id": job["job_id"],
                    "worker_release": RELEASE,
                }
            )
            capabilities.append(
                _capability(
                    job,
                    book=book,
                    market_key=key,
                    status="AVAILABLE",
                    reason="DISCOVERED",
                    observed_at=observed_at,
                )
            )
    for book in sorted(books):
        for key in sorted(requested):
            if (book, key) not in observed_pairs:
                capabilities.append(
                    _capability(
                        job,
                        book=book,
                        market_key=key,
                        status="NOT_AVAILABLE",
                        reason="MARKET_NOT_OPEN_YET",
                        observed_at=observed_at,
                    )
                )
    if not books:
        for key in sorted(requested):
            capabilities.append(
                _capability(
                    job,
                    book=None,
                    market_key=key,
                    status="NOT_AVAILABLE",
                    reason="BOOK_UNSUPPORTED",
                    observed_at=observed_at,
                )
            )
    return availability, capabilities


def _quotes(
    job: dict[str, Any], data: Any, observed_at: str, artifact_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    games = data if isinstance(data, list) else [data]
    requested = set(map(str, job.get("requested_market_keys", [])))
    availability: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    observed_pairs: set[tuple[str, str]] = set()
    books: set[str] = set()
    for game in games:
        if not isinstance(game, dict):
            continue
        provider_event_id = str(game.get("id", ""))
        if job.get("provider_event_id") and provider_event_id != job["provider_event_id"]:
            continue
        for bookmaker in game.get("bookmakers", []):
            if not isinstance(bookmaker, dict):
                continue
            book = str(bookmaker.get("key", ""))
            books.add(book)
            for market in bookmaker.get("markets", []):
                key = str(market.get("key", ""))
                if not key or (requested and key not in requested):
                    continue
                observed_pairs.add((book, key))
                availability.append(
                    {
                        "event_id": job["event_id"],
                        "provider": job["provider"],
                        "provider_event_id": provider_event_id,
                        "book": book,
                        "market_key": key,
                        "first_seen_at": observed_at,
                        "last_seen_at": observed_at,
                        "status": "AVAILABLE",
                        "provider_timestamp": market.get("last_update")
                        or bookmaker.get("last_update"),
                        "raw_evidence_id": artifact_id,
                        "worker_job_id": job["job_id"],
                        "worker_release": RELEASE,
                    }
                )
                capabilities.append(
                    _capability(
                        job,
                        book=book,
                        market_key=key,
                        status="AVAILABLE",
                        reason="QUOTES_RETURNED",
                        observed_at=observed_at,
                    )
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
                            "status": "SUSPENDED"
                            if outcome.get("suspended")
                            else "ACTIVE",
                            "observed_at": observed_at,
                            "provider_timestamp": market.get("last_update")
                            or bookmaker.get("last_update"),
                            "raw_evidence_id": artifact_id,
                            "worker_job_id": job["job_id"],
                            "worker_release": RELEASE,
                        }
                    )
    for book in sorted(books):
        for key in sorted(requested):
            if (book, key) not in observed_pairs:
                capabilities.append(
                    _capability(
                        job,
                        book=book,
                        market_key=key,
                        status="NOT_AVAILABLE",
                        reason="BOOK_UNSUPPORTED",
                        observed_at=observed_at,
                    )
                )
    return availability, quotes, capabilities


def _event_index(data: Any) -> list[dict[str, Any]]:
    games = data if isinstance(data, list) else []
    return [
        {
            "provider_event_id": str(game.get("id", "")),
            "home_team": str(game.get("home_team", "")),
            "away_team": str(game.get("away_team", "")),
            "commence_time": game.get("commence_time"),
        }
        for game in games
        if isinstance(game, dict) and game.get("id")
    ]


def _failure_capabilities(
    job: dict[str, Any], error: BoundedHttpError, observed_at: str
) -> list[dict[str, Any]]:
    if error.provider_code in PLAN_UNSUPPORTED_CODES or error.status_code in {401, 402, 403}:
        reason = "PLAN_UNSUPPORTED"
    elif error.status_code in {404, 422}:
        reason = "PROVIDER_UNSUPPORTED"
    else:
        reason = "REQUEST_FAILED"
    return [
        _capability(
            job,
            book=None,
            market_key=key,
            status="NOT_AVAILABLE",
            reason=reason,
            observed_at=observed_at,
        )
        for key in map(str, job.get("requested_market_keys", []))
    ]


def run(input_path: str, output_path: str) -> None:
    job = read_job(input_path)
    operation = str(job.get("operation", "HEADLINE"))
    if operation not in OPERATIONS:
        raise ValueError("unsupported market worker operation")
    endpoints = job.get("endpoints", [])
    fixtures = job.get("fixture_paths", [])
    if job.get("fixture_path") and not fixtures:
        fixtures = [job["fixture_path"]]
    request_count = len(fixtures) if fixtures else len(endpoints)
    maximum = min(int(job.get("max_requests", 0)), 50)
    if request_count < 1 or request_count > maximum:
        raise ValueError("market request list exceeds the bounded request budget")

    observed_at = utc_now()
    availability: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    raw_artifacts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    quota_before: dict[str, int | None] | None = None
    quota_after: dict[str, int | None] | None = None
    succeeded = 0
    items = fixtures or endpoints
    for index, item in enumerate(items):
        artifact_id = f"raw-{index}"
        try:
            if fixtures:
                raw = Path(str(item)).read_bytes()
                media_type = "application/json"
                source_url = f"file://{item}"
                headers: dict[str, str] = {}
            else:
                source_url = str(item)
                response = bounded_get(
                    source_url,
                    allowed_hosts=set(map(str, job.get("allowed_hosts", []))),
                    timeout=min(float(job.get("deadline_seconds", 60)), 60.0),
                    max_bytes=min(int(job.get("max_bytes", 5_000_000)), 10_000_000),
                    credential_env=str(job["credential_env"])
                    if job.get("credential_env")
                    else None,
                    credential_query_param=str(job["credential_query_param"])
                    if job.get("credential_query_param")
                    else None,
                )
                raw, media_type, headers = (
                    response.raw,
                    response.media_type,
                    response.headers,
                )
            raw_artifacts.append(
                artifact(raw, artifact_id=artifact_id, source_url=source_url, media_type=media_type)
            )
            data = json.loads(raw)
            if operation == "EVENT_INDEX":
                events.extend(_event_index(data))
            elif operation == "EVENT_DISCOVERY":
                found, observed_capabilities = _discovery(job, data, observed_at, artifact_id)
                availability.extend(found)
                capabilities.extend(observed_capabilities)
            else:
                found, observed_quotes, observed_capabilities = _quotes(
                    job, data, observed_at, artifact_id
                )
                availability.extend(found)
                quotes.extend(observed_quotes)
                capabilities.extend(observed_capabilities)
            succeeded += 1
            current_quota = _quota(headers)
            quota_before = quota_before or current_quota
            quota_after = current_quota
        except BoundedHttpError as error:
            capabilities.extend(_failure_capabilities(job, error, observed_at))
            failures.append(
                {
                    "request_index": index,
                    "reason": capabilities[-1]["reason"] if capabilities else "REQUEST_FAILED",
                    "status_code": error.status_code,
                    "provider_code": error.provider_code,
                }
            )
            current_quota = _quota(error.headers)
            quota_before = quota_before or current_quota
            quota_after = current_quota
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append({"request_index": index, "reason": type(error).__name__})

    finish_bundle(
        {
            "job_id": job["job_id"],
            "event_id": job["event_id"],
            "observed_at": observed_at,
            "provider": job["provider"],
            "operation": operation,
            "worker_release": RELEASE,
            "market_availability": availability,
            "quotes": quotes,
            "events": events,
            "provider_capabilities": capabilities,
            "request_stats": {
                "attempted": request_count,
                "succeeded": succeeded,
                "failed": request_count - succeeded,
                "quota_before": quota_before,
                "quota_after": quota_after,
            },
            "failures": failures,
            "raw_artifacts": raw_artifacts,
        },
        output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded sportsbook evidence collector")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("canary")
    command = sub.add_parser("run")
    command.add_argument("--input", required=True)
    command.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "canary":
        print(json.dumps({"worker": "grotto-sports-market-probe", "release": RELEASE, "status": "ok"}))
    else:
        run(args.input, args.output)


if __name__ == "__main__":
    main()
