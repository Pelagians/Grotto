from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = "sports-worker-bundle-v1"


@dataclass(frozen=True)
class HttpResult:
    raw: bytes
    media_type: str
    headers: dict[str, str]


class BoundedHttpError(RuntimeError):
    """Sanitized provider failure which never contains the credentialed URL."""

    def __init__(
        self,
        reason: str,
        *,
        status_code: int | None = None,
        provider_code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code
        self.provider_code = provider_code
        self.headers = headers or {}


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
) -> HttpResult:
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
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError("source response exceeds max_bytes")
            media_type = response.headers.get_content_type()
            response_headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower().startswith("x-requests-")
            }
        return HttpResult(raw=raw, media_type=media_type, headers=response_headers)
    except HTTPError as error:
        provider_code = None
        try:
            body = error.read(min(max_bytes, 64_000))
            payload = json.loads(body)
            if isinstance(payload, dict):
                provider_code = str(payload.get("error_code") or "") or None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        response_headers = {
            key.lower(): value
            for key, value in error.headers.items()
            if key.lower().startswith("x-requests-")
        }
        raise BoundedHttpError(
            "provider returned an HTTP error",
            status_code=error.code,
            provider_code=provider_code,
            headers=response_headers,
        ) from None
    except (URLError, TimeoutError):
        raise BoundedHttpError("provider request failed") from None
