from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


def workspace_dir() -> Path:
    return Path(os.getenv("OPENQUAD_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))


def tasks_root() -> Path:
    return workspace_dir() / "tasks"


def ensure_safe_task_id(task_id: str) -> str:
    if task_id in {".", ".."} or not SAFE_TASK_ID.match(task_id):
        raise ValueError("task_id may only contain letters, numbers, '.', '_', ':', or '-'")
    return task_id


def task_dir(task_id: str) -> Path:
    safe = ensure_safe_task_id(task_id)
    root = tasks_root().resolve(strict=False)
    path = (root / safe).resolve(strict=False)
    if path == root or root not in path.parents:
        raise ValueError("task_id must resolve under the OpenQuad tasks directory")
    return path


def prepare_task_dir(task_id: str) -> Path:
    path = task_dir(task_id)
    (path / "artifacts").mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def result_path(task_id: str) -> Path:
    return task_dir(task_id) / "result.json"


def status_path(task_id: str) -> Path:
    return task_dir(task_id) / "status.json"


def task_path(task_id: str) -> Path:
    return task_dir(task_id) / "task.json"


def artifact_manifest_path(task_id: str) -> Path:
    return task_dir(task_id) / "artifact-manifest.json"


def events_path(task_id: str) -> Path:
    return task_dir(task_id) / "events.jsonl"
