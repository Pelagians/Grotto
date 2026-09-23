#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from worker_common import artifact, bounded_get, finish_bundle, read_job, utc_now

RELEASE = os.environ.get("GROTTO_BUILD_REVISION", "grotto-sports-source-probe-dev")


def run(input_path: str, output_path: str) -> None:
    job = read_job(input_path)
    sources = job.get("sources", [])
    if not isinstance(sources, list) or len(sources) > int(job.get("max_requests", 20)):
        raise ValueError("source list exceeds max_requests")
    allowed_classes = set(map(str, job.get("allowed_source_classes", [])))
    allowed_hosts = set(map(str, job.get("allowed_hosts", [])))
    attempts: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        source_class = str(source.get("source_class", ""))
        url = str(source.get("url", ""))
        watch_id = str(source.get("source_watch_id", ""))
        if source_class not in allowed_classes:
            failures.append(
                {"source_watch_id": watch_id, "reason": "SOURCE_CLASS_NOT_ALLOWED"}
            )
            continue
        try:
            if source.get("fixture_path"):
                raw = Path(str(source["fixture_path"])).read_bytes()
                media = str(source.get("media_type", "text/html"))
                artifact_url = f"file://{source['fixture_path']}"
            else:
                response = bounded_get(
                    url,
                    allowed_hosts=allowed_hosts,
                    timeout=min(float(job.get("deadline_seconds", 90)), 90),
                    max_bytes=min(
                        int(job.get("max_bytes_per_source", 2_000_000)), 5_000_000
                    ),
                )
                raw, media = response.raw, response.media_type
                artifact_url = url
            artifact_id = f"raw-{index}"
            artifacts.append(
                artifact(
                    raw,
                    artifact_id=artifact_id,
                    source_url=artifact_url,
                    media_type=media,
                )
            )
            attempts.append(
                {
                    "source_watch_id": watch_id,
                    "url": url,
                    "result": "WATCHED_UPDATE_FOUND",
                    "raw_evidence_id": artifact_id,
                }
            )
            candidates.append(
                {
                    "source_watch_id": watch_id,
                    "raw_evidence_id": artifact_id,
                    "source_class": source_class,
                    "content_excerpt": raw.decode("utf-8", errors="replace")[:1000],
                    "requires_nyra_normalization": True,
                }
            )
        except (
            OSError,
            TimeoutError,
            ValueError,
        ) as error:  # isolate one source failure
            failures.append(
                {"source_watch_id": watch_id, "reason": type(error).__name__}
            )
            attempts.append(
                {"source_watch_id": watch_id, "url": url, "result": "WATCH_FAILED"}
            )
    finish_bundle(
        {
            "job_id": job["job_id"],
            "team_id": job["team_id"],
            "event_id": job["event_id"],
            "observed_at": utc_now(),
            "worker_release": RELEASE,
            "sources_attempted": attempts,
            "raw_artifacts": artifacts,
            "candidate_claim_material": candidates,
            "failures": failures,
        },
        output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded public sports-source collector"
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
                    "worker": "grotto-sports-source-probe",
                    "release": RELEASE,
                    "status": "ok",
                }
            )
        )
    else:
        run(args.input, args.output)


if __name__ == "__main__":
    main()
