from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openquad_workerd.server import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_manifests_and_examples_are_validated_by_script():
    from scripts.validate_openquad_contracts import validate_repo

    result = validate_repo(ROOT)
    assert result["schemas"] >= 6
    assert result["manifests"] == 4
    assert result["examples"] >= 12


def test_worker_serves_manifest_and_capabilities(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(tmp_path / "workspace"))

    client = TestClient(create_app())

    health = client.get("/healthz")
    assert health.status_code == 200
    manifest = client.get("/openquad/v1/manifest").json()
    assert manifest["worker"]["name"] == "openquad-documents"
    capabilities = client.get("/openquad/v1/capabilities").json()
    assert "documents.convert" in capabilities["capabilities"]


def test_worker_rejects_unknown_task_type_cleanly(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(tmp_path / "workspace"))
    client = TestClient(create_app())

    response = client.post(
        "/openquad/v1/tasks",
        json={
            "task_id": "task-unknown",
            "idempotency_key": "idem-unknown",
            "capability": "documents.convert",
            "task_type": "not-a-real-task",
            "input": {},
            "constraints": {"max_runtime_seconds": 300, "network_policy": "none", "allowed_domains": [], "write_scope": "task"},
            "policy": {"decision": "allowed", "reason": "test", "policy_version": "v0.1"},
            "provenance": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_task_type"


def test_worker_rejects_task_id_path_traversal(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    for task_id in [".", ".."]:
        response = client.post(
            "/openquad/v1/tasks",
            json={
                "task_id": task_id,
                "idempotency_key": f"idem-{task_id}",
                "capability": "documents.convert",
                "task_type": "convert_pdf_to_text",
                "input": {},
                "constraints": {"max_runtime_seconds": 300, "network_policy": "none", "allowed_domains": [], "write_scope": "task"},
                "policy": {"decision": "allowed", "reason": "test", "policy_version": "v0.1"},
                "provenance": {},
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_task_id"

    assert not (workspace / "task.json").exists()
    assert not (workspace / "result.json").exists()
    assert not (workspace / "events.jsonl").exists()
    assert not (workspace / "artifact-manifest.json").exists()


def test_worker_writes_task_result_events_and_artifact_manifest(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    response = client.post(
        "/openquad/v1/tasks",
        json={
            "task_id": "task-doc-convert-001",
            "idempotency_key": "idem-doc-convert-001",
            "capability": "documents.convert",
            "task_type": "convert_pdf_to_text",
            "input": {"source_uri": "file:///workspace/inquiry.pdf"},
            "constraints": {"max_runtime_seconds": 300, "network_policy": "none", "allowed_domains": [], "write_scope": "task"},
            "policy": {"decision": "allowed", "reason": "read-only", "policy_version": "v0.1"},
            "provenance": {"orchestrator": "test"},
        },
    )

    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "not_implemented"

    task_dir = workspace / "tasks" / "task-doc-convert-001"
    assert (task_dir / "task.json").is_file()
    assert (task_dir / "result.json").is_file()
    assert (task_dir / "events.jsonl").is_file()
    assert (task_dir / "artifact-manifest.json").is_file()

    events = [json.loads(line) for line in (task_dir / "events.jsonl").read_text().splitlines()]
    assert [event["event_type"] for event in events] == [
        "task.accepted",
        "task.started",
        "task.failed",
    ]

    fetched = client.get("/openquad/v1/tasks/task-doc-convert-001").json()
    assert fetched["task_id"] == "task-doc-convert-001"
    artifacts = client.get("/openquad/v1/tasks/task-doc-convert-001/artifacts").json()
    assert artifacts["task_id"] == "task-doc-convert-001"
    assert artifacts["artifacts"] == []
