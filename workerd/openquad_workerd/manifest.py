
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "openquad.worker.v0.1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_manifest_path() -> Path:
    template = os.getenv("OPENQUAD_TEMPLATE", "communications-calendar")
    image_path = Path("/usr/share/openquad/templates") / template / "openquad.manifest.json"
    if image_path.exists():
        return image_path
    return _repo_root() / "templates" / template / "openquad.manifest.json"


def manifest_path() -> Path:
    configured = os.getenv("OPENQUAD_MANIFEST_PATH")
    return Path(configured) if configured else default_manifest_path()


def load_manifest() -> dict[str, Any]:
    path = manifest_path()
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"unsupported OpenQuad contract version in {path}: {manifest.get('contract_version')}")
    return manifest


def worker_name(manifest: dict[str, Any]) -> str:
    worker = manifest.get("worker") or {}
    return str(worker.get("name") or manifest.get("image") or "openquad-worker")


def capability_names(manifest: dict[str, Any]) -> list[str]:
    return [str(capability["name"]) for capability in manifest.get("capabilities", [])]


def capability_task_types(manifest: dict[str, Any], capability_name: str) -> list[str]:
    for capability in manifest.get("capabilities", []):
        if capability.get("name") == capability_name:
            return list(capability.get("task_types") or [])
    return []


def supports_task(manifest: dict[str, Any], capability_name: str, task_type: str) -> bool:
    return task_type in capability_task_types(manifest, capability_name)


def capabilities_response(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": manifest.get("contract_version"),
        "worker": manifest.get("worker", {}).get("name"),
        "capabilities": capability_names(manifest),
        "supported_task_types": manifest.get("supported_task_types", []),
        "details": manifest.get("capabilities", []),
    }
