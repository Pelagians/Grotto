from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

SCHEMA_VERSION = "sports-worker-bundle-v1"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_job(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not str(payload.get("job_id", "")).strip():
        raise ValueError("job input requires a non-empty job_id")
    return payload


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "bundle_digest"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def finish_bundle(payload: dict[str, Any], path: str) -> None:
    payload["schema_version"] = SCHEMA_VERSION
    payload["bundle_digest"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def artifact(
    raw: bytes, *, artifact_id: str, source_url: str, media_type: str
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "source_url": source_url,
        "media_type": media_type,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


def bounded_get(
    url: str,
    *,
    allowed_hosts: set[str],
    timeout: float,
    max_bytes: int,
    credential_env: str | None = None,
    credential_query_param: str | None = None,
) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname not in allowed_hosts
    ):
        raise ValueError("source URL is outside the approved HTTPS egress hosts")
    headers = {
        "Accept": "application/json,text/html",
        "User-Agent": "grotto-sports-worker/1",
    }
    if credential_env:
        secret = os.environ.get(credential_env, "")
        if not secret:
            raise ValueError("required provider credential is not available")
        if credential_query_param:
            query = parse_qsl(parsed.query, keep_blank_values=True)
            query.append((credential_query_param, secret))
            url = urlunparse(parsed._replace(query=urlencode(query)))
        else:
            headers["Authorization"] = f"Bearer {secret}"
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("source response exceeds max_bytes")
        media_type = response.headers.get_content_type()
    return raw, media_type
