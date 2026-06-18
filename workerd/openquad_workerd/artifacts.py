
from __future__ import annotations

import hashlib
from pathlib import Path

from .contracts import Artifact, ArtifactManifest
from .events import utcnow_iso
from .task_store import artifact_manifest_path, write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_from_file(path: Path, *, kind: str, content_type: str) -> Artifact:
    return Artifact(
        kind=kind,
        uri=path.resolve().as_uri(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        content_type=content_type,
    )


def write_artifact_manifest(task_id: str, artifacts: list[Artifact] | None = None) -> ArtifactManifest:
    manifest = ArtifactManifest(task_id=task_id, created_at=utcnow_iso(), artifacts=artifacts or [])
    write_json(artifact_manifest_path(task_id), manifest.model_dump(mode="json"))
    return manifest
