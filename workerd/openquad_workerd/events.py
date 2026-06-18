
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .task_store import events_path


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(task_id: str, event_type: str, event_json: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "event_type": event_type,
        "task_id": task_id,
        "created_at": utcnow_iso(),
    }
    if event_json is not None:
        event["event_json"] = event_json
    path = events_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=False) + "\n")
    return event
