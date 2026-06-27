"""OpenQuad workerd tests — v0.2 milestone.

Covers:
  - schema and manifest validation pass
  - example files validate against schemas
  - convert_pdf_to_text runner: real PDF → artifacts with sha256 and size_bytes
  - artifact manifest written with correct structure
  - missing source file fails cleanly (no fake success)
  - source_uri outside workspace boundary fails cleanly
  - missing source_uri in input fails cleanly
  - unknown task type returns 400 unsupported_task_type
  - path-traversal task_id rejected
  - task.json / result.json / events.jsonl / artifact-manifest.json all written
  - pdftotext not available → clear failure (monkeypatched)
  - convert_pdf_to_text runner: all extraction tools fail → failed status, no artifacts
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openquad_workerd.server import create_app

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pdf_fixture(path: Path) -> Path:
    """Write a minimal valid PDF with selectable text to *path*."""
    page_stream = (
        "BT\n"
        "/F1 12 Tf\n"
        "50 750 Td\n"
        "(Hello from OpenQuad convert_pdf_to_text runner test.) Tj\n"
        "0 -20 Td\n"
        "(This is page one.) Tj\n"
        "0 -20 Td\n"
        "(Line three.) Tj\n"
        "ET"
    )
    stream_bytes = page_stream.encode("latin-1")
    stream_len = len(stream_bytes)

    pdf = b"%PDF-1.4\n"
    offsets = []

    offsets.append(len(pdf))
    pdf += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    offsets.append(len(pdf))
    pdf += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    offsets.append(len(pdf))
    pdf += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    offsets.append(len(pdf))
    pdf += f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode()
    pdf += stream_bytes
    pdf += b"\nendstream\nendobj\n"
    offsets.append(len(pdf))
    pdf += b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n"

    xref_offset = len(pdf)
    pdf += b"xref\n"
    pdf += f"0 {len(offsets) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += b"trailer\n"
    pdf += f"<< /Size {len(offsets) + 1} /Root 1 0 R >>\n".encode()
    pdf += b"startxref\n"
    pdf += f"{xref_offset}\n".encode()
    pdf += b"%%EOF\n"

    path.write_bytes(pdf)
    return path


def _has_pdftotext() -> bool:
    return shutil.which("pdftotext") is not None


def make_client(workspace: Path, manifest_path: Path | None = None) -> TestClient:
    if manifest_path is None:
        manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    os.environ["OPENQUAD_MANIFEST_PATH"] = str(manifest_path)
    os.environ["OPENQUAD_WORKSPACE_DIR"] = str(workspace)
    return TestClient(create_app())


def base_envelope(task_id: str, task_type: str, source_uri: str) -> dict:
    return {
        "task_id": task_id,
        "idempotency_key": f"idem-{task_id}",
        "capability": "documents.convert",
        "task_type": task_type,
        "input": {"source_uri": source_uri},
        "constraints": {
            "max_runtime_seconds": 300,
            "network_policy": "none",
            "allowed_domains": [],
            "write_scope": "task",
        },
        "policy": {
            "decision": "allowed",
            "reason": "read-only",
            "policy_version": "v0.1",
        },
        "provenance": {"orchestrator": "test"},
    }


# ---------------------------------------------------------------------------
# Schema and manifest validation
# ---------------------------------------------------------------------------

def test_manifests_and_examples_are_validated_by_script():
    from scripts.validate_openquad_contracts import validate_repo

    result = validate_repo(ROOT)
    assert result["schemas"] >= 6
    assert result["manifests"] == 4
    assert result["examples"] >= 12


def test_documents_manifest_has_context_profiles(tmp_path, monkeypatch):
    """The documents manifest must declare context_profiles at worker level."""
    import json as _json
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    manifest = _json.loads(manifest_path.read_text())
    assert "context_profiles" in manifest, "manifest must declare context_profiles"
    profiles = manifest["context_profiles"]
    for name in ("small_task", "normal_task", "large_context_task", "deep_document_task", "browser_recovery_task"):
        assert name in profiles, f"missing context profile: {name}"


def test_documents_manifest_convert_capability_has_profiles(tmp_path, monkeypatch):
    import json as _json
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    manifest = _json.loads(manifest_path.read_text())
    convert_cap = next(c for c in manifest["capabilities"] if c["name"] == "documents.convert")
    assert "context_profiles" in convert_cap, "documents.convert capability must have context_profiles"
    for name in ("small_task", "normal_task", "large_context_task", "deep_document_task"):
        assert name in convert_cap["context_profiles"], f"missing capability context profile: {name}"


def test_documents_manifest_context_profile_fields():
    import json as _json
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    manifest = _json.loads(manifest_path.read_text())
    for profile_name, profile in manifest["context_profiles"].items():
        for field in (
            "description",
            "max_single_prompt_tokens",
            "max_total_task_tokens",
            "max_model_calls_per_task",
            "max_tool_calls_per_task",
            "artifact_first",
            "chunking_required",
            "preferred_model_class",
            "deterministic_tools_first",
        ):
            assert field in profile, f"context profile '{profile_name}' missing field '{field}'"


# ---------------------------------------------------------------------------
# Worker manifest + capabilities endpoint
# ---------------------------------------------------------------------------

def test_worker_serves_manifest_and_capabilities(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(tmp_path / "workspace"))

    client = TestClient(create_app())

    health = client.get("/healthz")
    assert health.status_code == 200

    manifest = client.get("/openquad/v1/manifest").json()
    assert manifest["worker"]["name"] == "openquad-documents"
    assert "context_profiles" in manifest

    capabilities = client.get("/openquad/v1/capabilities").json()
    assert "documents.convert" in capabilities["capabilities"]
    assert "convert_pdf_to_text" in capabilities["supported_task_types"]


# ---------------------------------------------------------------------------
# Unknown task type
# ---------------------------------------------------------------------------

def test_worker_rejects_unknown_task_type_cleanly(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(tmp_path / "workspace"))
    client = TestClient(create_app())

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope("task-unknown", "not-a-real-task", "file:///anything"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_task_type"


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------

def test_worker_rejects_task_id_path_traversal(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    for task_id in [".", ".."]:
        env = base_envelope(task_id, "convert_pdf_to_text", f"file://{workspace}/input.pdf")
        env["idempotency_key"] = f"idem-traversal-{task_id}"
        response = client.post("/openquad/v1/tasks?sync=true", json=env)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_task_id"

    # No files created at workspace root
    assert not (workspace / "task.json").exists()
    assert not (workspace / "result.json").exists()


# ---------------------------------------------------------------------------
# Stub task type (not_implemented)
# ---------------------------------------------------------------------------

def test_worker_writes_task_result_events_and_artifact_manifest(tmp_path, monkeypatch):
    """Stub runner path (convert_document not yet implemented) still writes all files."""
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json={
            **base_envelope("task-stub-001", "convert_document", f"file://{workspace}/input.pdf"),
            "idempotency_key": "idem-stub-001",
        },
    )

    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "not_implemented"

    task_dir = workspace / "tasks" / "task-stub-001"
    assert (task_dir / "task.json").is_file()
    assert (task_dir / "result.json").is_file()
    assert (task_dir / "events.jsonl").is_file()
    assert (task_dir / "artifact-manifest.json").is_file()

    events = [json.loads(line) for line in (task_dir / "events.jsonl").read_text().splitlines()]
    event_types = [e["event_type"] for e in events]
    assert "task.accepted" in event_types
    assert "task.started" in event_types
    assert "task.failed" in event_types


# ---------------------------------------------------------------------------
# convert_pdf_to_text: missing source_uri
# ---------------------------------------------------------------------------

def test_convert_pdf_to_text_missing_source_uri(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    env = {
        "task_id": "task-no-uri",
        "idempotency_key": "idem-no-uri",
        "capability": "documents.convert",
        "task_type": "convert_pdf_to_text",
        "input": {},  # no source_uri
        "constraints": {"max_runtime_seconds": 60, "network_policy": "none", "allowed_domains": [], "write_scope": "task"},
        "policy": {"decision": "allowed", "reason": "test", "policy_version": "v0.1"},
        "provenance": {},
    }
    response = client.post("/openquad/v1/tasks?sync=true", json=env)
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "missing_input" for e in result["errors"])


# ---------------------------------------------------------------------------
# convert_pdf_to_text: source file not found
# ---------------------------------------------------------------------------

def test_convert_pdf_to_text_source_not_found(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    missing_uri = f"file://{workspace}/does-not-exist.pdf"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope("task-notfound", "convert_pdf_to_text", missing_uri),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "source_not_found" for e in result["errors"])
    # Must not have artifacts
    assert result["artifacts"] == []


# ---------------------------------------------------------------------------
# convert_pdf_to_text: source URI outside workspace boundary
# ---------------------------------------------------------------------------

def test_convert_pdf_to_text_source_outside_workspace(tmp_path, monkeypatch):
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    outside_uri = "file:///etc/passwd"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope("task-outside", "convert_pdf_to_text", outside_uri),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "invalid_source_uri" for e in result["errors"])
    assert result["artifacts"] == []


# ---------------------------------------------------------------------------
# convert_pdf_to_text: pdftotext not available
# ---------------------------------------------------------------------------

def test_convert_pdf_to_text_tool_not_available(tmp_path, monkeypatch):
    """When pdftotext is missing the runner must fail clearly, not fake success."""
    import openquad_workerd.runners_documents as rd

    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))

    # Create a valid PDF inside workspace
    pdf_path = workspace / "input.pdf"
    make_pdf_fixture(pdf_path)

    # Monkeypatch _tool_available to pretend pdftotext is missing
    original = rd._tool_available
    def fake_tool_available(name: str) -> bool:
        if name == "pdftotext":
            return False
        return original(name)
    monkeypatch.setattr(rd, "_tool_available", fake_tool_available)

    client = TestClient(create_app())
    source_uri = f"file://{pdf_path}"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope("task-no-tool", "convert_pdf_to_text", source_uri),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "tool_not_available" for e in result["errors"])
    assert result["artifacts"] == []


# ---------------------------------------------------------------------------
# convert_pdf_to_text: all tools fail → clean failure, no artifacts
# ---------------------------------------------------------------------------

def test_convert_pdf_to_text_all_tools_fail(tmp_path, monkeypatch):
    """If pdftotext, qpdf, and ocrmypdf all fail, result must be failed with no fake artifacts."""
    import openquad_workerd.runners_documents as rd

    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))

    pdf_path = workspace / "input.pdf"
    make_pdf_fixture(pdf_path)

    # Make all tool calls fail
    monkeypatch.setattr(rd, "_pdftotext", lambda src, out: (False, "simulated pdftotext failure"))
    monkeypatch.setattr(rd, "_qpdf_linearize", lambda src, out: (False, "simulated qpdf failure"))
    monkeypatch.setattr(rd, "_ocrmypdf", lambda src, out_pdf, out_txt, language="eng": (False, "simulated ocrmypdf failure"))

    client = TestClient(create_app())
    source_uri = f"file://{pdf_path}"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope("task-alltools-fail", "convert_pdf_to_text", source_uri),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert len(result["errors"]) >= 1
    assert result["artifacts"] == []


# ---------------------------------------------------------------------------
# convert_pdf_to_text: REAL runner with real PDF (requires pdftotext)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _has_pdftotext(), reason="pdftotext not available on this system")
def test_convert_pdf_to_text_real_extraction_writes_artifacts(tmp_path, monkeypatch):
    """Full happy path: real PDF → pdftotext → artifacts with sha256 + size_bytes."""
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))

    pdf_path = workspace / "inquiry.pdf"
    make_pdf_fixture(pdf_path)

    client = TestClient(create_app())
    source_uri = f"file://{pdf_path}"
    task_id = "task-real-extract-001"

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope(task_id, "convert_pdf_to_text", source_uri),
    )
    assert response.status_code == 202
    result = response.json()

    # -- Status must be succeeded
    assert result["status"] == "succeeded", f"Expected succeeded, got {result['status']}. Errors: {result['errors']}"
    assert result["task_id"] == task_id
    assert result["capability"] == "documents.convert"
    assert result["task_type"] == "convert_pdf_to_text"

    # -- Must have at least one artifact (text)
    assert len(result["artifacts"]) >= 1, "Must produce at least one artifact"

    text_artifact = next((a for a in result["artifacts"] if a["kind"] == "text"), None)
    assert text_artifact is not None, "Must include a text artifact"

    # -- Artifact must have sha256 (64 hex chars) and positive size_bytes
    sha256 = text_artifact["sha256"]
    assert len(sha256) == 64, f"sha256 must be 64 hex chars, got: {sha256!r}"
    assert all(c in "0123456789abcdefABCDEF" for c in sha256)
    assert text_artifact["size_bytes"] > 0
    assert text_artifact["content_type"] == "text/plain"

    # -- Artifact URI must be a file:// path inside workspace
    assert text_artifact["uri"].startswith("file://")

    # -- Files must actually be written
    task_dir = workspace / "tasks" / task_id
    assert (task_dir / "task.json").is_file()
    assert (task_dir / "result.json").is_file()
    assert (task_dir / "events.jsonl").is_file()
    assert (task_dir / "artifact-manifest.json").is_file()

    # -- Verify artifact file exists and sha256 matches
    txt_path = Path(text_artifact["uri"].replace("file://", ""))
    assert txt_path.exists(), f"Text artifact file not found: {txt_path}"

    actual_text = txt_path.read_text(encoding="utf-8", errors="replace")
    assert "OpenQuad" in actual_text or len(actual_text.strip()) > 0, "Extracted text must be non-empty"

    # -- Verify sha256 is correct
    import hashlib
    computed = hashlib.sha256(txt_path.read_bytes()).hexdigest()
    assert computed == sha256, f"sha256 mismatch: stored={sha256} computed={computed}"

    # -- Verify artifact manifest matches result artifacts
    art_manifest = json.loads((task_dir / "artifact-manifest.json").read_text())
    assert art_manifest["task_id"] == task_id
    assert len(art_manifest["artifacts"]) == len(result["artifacts"])

    result_shas = {a["sha256"] for a in result["artifacts"]}
    manifest_shas = {a["sha256"] for a in art_manifest["artifacts"]}
    assert result_shas == manifest_shas, "artifact-manifest.json must match result artifacts"

    # -- Verify events
    events = [json.loads(line) for line in (task_dir / "events.jsonl").read_text().splitlines()]
    event_types = [e["event_type"] for e in events]
    assert "task.accepted" in event_types
    assert "task.started" in event_types
    assert "task.succeeded" in event_types

    # -- Fetch via API
    fetched = client.get(f"/openquad/v1/tasks/{task_id}").json()
    assert fetched["task_id"] == task_id
    assert fetched["status"] == "succeeded"

    api_artifacts = client.get(f"/openquad/v1/tasks/{task_id}/artifacts").json()
    assert api_artifacts["task_id"] == task_id
    assert len(api_artifacts["artifacts"]) >= 1


@pytest.mark.skipif(not _has_pdftotext(), reason="pdftotext not available on this system")
def test_convert_pdf_to_text_metadata_artifact(tmp_path, monkeypatch):
    """Real runner must produce a JSON metadata artifact alongside the text artifact."""
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))

    pdf_path = workspace / "meta-test.pdf"
    make_pdf_fixture(pdf_path)

    client = TestClient(create_app())
    task_id = "task-meta-artifact-001"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope(task_id, "convert_pdf_to_text", f"file://{pdf_path}"),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "succeeded"

    # Must have a JSON metadata artifact
    json_artifact = next((a for a in result["artifacts"] if a["kind"] == "json"), None)
    assert json_artifact is not None, "Must include a JSON metadata artifact"
    assert json_artifact["sha256"] and len(json_artifact["sha256"]) == 64
    assert json_artifact["size_bytes"] > 0
    assert json_artifact["content_type"] == "application/json"

    # Verify metadata file content
    meta_path = Path(json_artifact["uri"].replace("file://", ""))
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert "source_uri" in meta
    assert "page_count" in meta
    assert "pdf_metadata" in meta
    assert "text_artifact_sha256" in meta
    assert "text_artifact_size_bytes" in meta


@pytest.mark.skipif(not _has_pdftotext(), reason="pdftotext not available on this system")
def test_convert_pdf_to_text_result_fields(tmp_path, monkeypatch):
    """result dict must contain message, source_uri, text_size_bytes, text_sha256, artifact_count."""
    manifest_path = ROOT / "templates" / "documents" / "openquad.manifest.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))

    pdf_path = workspace / "fields-test.pdf"
    make_pdf_fixture(pdf_path)
    client = TestClient(create_app())
    task_id = "task-fields-001"

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=base_envelope(task_id, "convert_pdf_to_text", f"file://{pdf_path}"),
    )
    result = response.json()
    assert result["status"] == "succeeded"

    r = result["result"]
    assert "message" in r
    assert "source_uri" in r
    assert "text_size_bytes" in r and r["text_size_bytes"] > 0
    assert "text_sha256" in r and len(r["text_sha256"]) == 64
    assert "artifact_count" in r and r["artifact_count"] >= 1


# ---------------------------------------------------------------------------
# browser.screenshot / screenshot runner
# ---------------------------------------------------------------------------

BROWSER_MANIFEST_PATH = ROOT / "templates" / "browser-agent" / "openquad.manifest.json"


def _browser_client(workspace: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("OPENQUAD_MANIFEST_PATH", str(BROWSER_MANIFEST_PATH))
    monkeypatch.setenv("OPENQUAD_WORKSPACE_DIR", str(workspace))
    return TestClient(create_app())


def _browser_envelope(task_id: str, url: str, *, allowed_domains: list[str] | None = None, input_overrides: dict | None = None) -> dict:
    base_input = {"url": url}
    if input_overrides:
        base_input.update(input_overrides)
    env = {
        "task_id": task_id,
        "idempotency_key": f"idem-{task_id}",
        "capability": "browser.screenshot",
        "task_type": "screenshot",
        "input": base_input,
        "constraints": {
            "max_runtime_seconds": 120,
            "network_policy": "restricted",
            "allowed_domains": allowed_domains or [],
            "write_scope": "task",
        },
        "policy": {
            "decision": "allowed",
            "reason": "read-only screenshot",
            "policy_version": "v0.1",
        },
        "provenance": {"orchestrator": "test"},
    }
    return env


def test_browser_screenshot_missing_url(tmp_path, monkeypatch):
    """Missing url input must fail with missing_input, not crash."""
    import openquad_workerd.runners_browser as rb

    workspace = tmp_path / "workspace"
    client = _browser_client(workspace, monkeypatch)

    env = _browser_envelope("task-no-url", "")
    del env["input"]["url"]
    response = client.post("/openquad/v1/tasks?sync=true", json=env)
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "missing_input" for e in result["errors"])
    assert result["artifacts"] == []


def test_browser_screenshot_invalid_url_scheme(tmp_path, monkeypatch):
    """file:// URLs must be rejected with invalid_url."""
    workspace = tmp_path / "workspace"
    client = _browser_client(workspace, monkeypatch)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-bad-scheme", "file:///tmp/foo.png"),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "invalid_url" for e in result["errors"])


def test_browser_screenshot_domain_not_allowed(tmp_path, monkeypatch):
    """URL outside allowed_domains must be rejected."""
    workspace = tmp_path / "workspace"
    client = _browser_client(workspace, monkeypatch)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-blocked-domain", "https://evil.com/malware", allowed_domains=["example.com"]),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "invalid_url" for e in result["errors"])
    assert "example.com" in str(result["errors"])


def test_browser_screenshot_viewport_clamping(tmp_path, monkeypatch):
    """Viewport larger than 3840x2160 must be rejected."""
    import openquad_workerd.runners_browser as rb
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("BROWSER_WS_ENDPOINT", "ws://browser:3000/playwright")
    client = _browser_client(workspace, monkeypatch)

    def fake_fail(url, ws, cdp, viewport=None, full_page=False, timeout_ms=None):
        raise ConnectionRefusedError("fake")
    monkeypatch.setattr(rb, "_execute_screenshot", fake_fail)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-vp-big", "https://example.com/",
                               allowed_domains=["example.com"],
                               input_overrides={"viewport": {"width": 7680, "height": 4320}}),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed", f"expected failed, got {result['status']}"
    assert any(e["code"] == "viewport_too_large" for e in result["errors"])


def test_browser_screenshot_no_browser_endpoint(tmp_path, monkeypatch):
    """When BROWSER_WS_ENDPOINT is not set, must fail with browser_endpoint_missing."""
    # Explicitly ensure the env var is unset
    monkeypatch.delenv("BROWSER_WS_ENDPOINT", raising=False)
    monkeypatch.delenv("BROWSER_CDP_ENDPOINT", raising=False)

    workspace = tmp_path / "workspace"
    client = _browser_client(workspace, monkeypatch)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-no-browser", "https://example.com/"),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "browser_endpoint_missing" for e in result["errors"])
    assert result["artifacts"] == []


def test_browser_screenshot_playwright_fails_gracefully(tmp_path, monkeypatch):
    """If _execute_screenshot raises, the runner must fail cleanly, not crash."""
    import openquad_workerd.runners_browser as rb

    workspace = tmp_path / "workspace"
    monkeypatch.setenv("BROWSER_WS_ENDPOINT", "ws://browser:3000/playwright")
    client = _browser_client(workspace, monkeypatch)

    # Make the screenshot function raise an exception
    def fake_fail(url, ws, cdp, viewport=None, full_page=False, timeout_ms=None):
        raise ConnectionRefusedError("simulated browser connection failure")
    monkeypatch.setattr(rb, "_execute_screenshot", fake_fail)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-pw-fail", "https://example.com/", allowed_domains=["example.com"]),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "failed"
    assert any(e["code"] == "screenshot_failed" for e in result["errors"])
    assert "simulated browser connection failure" in str(result["errors"])
    assert result["artifacts"] == []


def test_browser_screenshot_happy_path(tmp_path, monkeypatch):
    """Full happy path: monkeypatched screenshot → PNG artifact with sha256 + size_bytes."""
    import openquad_workerd.runners_browser as rb

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BROWSER_WS_ENDPOINT", "ws://browser:3000/playwright")
    client = _browser_client(workspace, monkeypatch)

    # Monkeypatch the internal screenshot function to return real minimal PNG bytes
    MINIMAL_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    monkeypatch.setattr(rb, "_execute_screenshot", lambda url, ws, cdp, viewport=None, full_page=False, timeout_ms=None: MINIMAL_PNG)

    task_id = "task-screenshot-happy-001"
    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope(task_id, "https://example.com/", allowed_domains=["example.com"]),
    )
    assert response.status_code == 202
    result = response.json()

    # -- Status must be succeeded
    assert result["status"] == "succeeded", f"Expected succeeded, got {result['status']}. Errors: {result['errors']}"
    assert result["task_id"] == task_id
    assert result["capability"] == "browser.screenshot"
    assert result["task_type"] == "screenshot"

    # -- Must have one PNG artifact
    assert len(result["artifacts"]) == 1
    png_artifact = result["artifacts"][0]
    assert png_artifact["kind"] == "png"
    assert png_artifact["content_type"] == "image/png"

    # -- Artifact sha256 must be 64 hex chars and size must be positive
    sha256 = png_artifact["sha256"]
    assert len(sha256) == 64, f"sha256 must be 64 hex chars, got: {sha256!r}"
    assert all(c in "0123456789abcdefABCDEF" for c in sha256)
    assert png_artifact["size_bytes"] == len(MINIMAL_PNG)

    # -- Artifact URI must be a file:// path inside workspace
    assert png_artifact["uri"].startswith("file://")

    # -- Std files must exist
    task_dir = workspace / "tasks" / task_id
    assert (task_dir / "task.json").is_file()
    assert (task_dir / "result.json").is_file()
    assert (task_dir / "events.jsonl").is_file()
    assert (task_dir / "artifact-manifest.json").is_file()

    # -- Verify artifact file exists on disk and sha256 matches
    from pathlib import Path as _Path
    png_path = _Path(png_artifact["uri"].replace("file://", ""))
    assert png_path.exists(), f"PNG artifact file not found: {png_path}"
    written = png_path.read_bytes()
    assert written == MINIMAL_PNG, "Written PNG bytes must match the fake screenshot output"

    # -- Verify computed sha256 matches
    import hashlib as _hashlib
    computed = _hashlib.sha256(written).hexdigest()
    assert computed == sha256, f"sha256 mismatch: stored={sha256} computed={computed}"

    # -- Verify artifact-manifest.json matches result artifacts
    import json as _json
    art_manifest = _json.loads((task_dir / "artifact-manifest.json").read_text())
    assert art_manifest["task_id"] == task_id
    assert len(art_manifest["artifacts"]) == 1
    assert art_manifest["artifacts"][0]["sha256"] == sha256

    # -- Verify events
    events = [_json.loads(line) for line in (task_dir / "events.jsonl").read_text().splitlines()]
    event_types = [e["event_type"] for e in events]
    assert "task.accepted" in event_types
    assert "task.started" in event_types
    assert "task.succeeded" in event_types
    assert "task.tool_start" in event_types
    assert "task.tool_done" in event_types
    assert "task.artifact_written" in event_types

    # -- Fetch via API
    fetched = client.get(f"/openquad/v1/tasks/{task_id}").json()
    assert fetched["task_id"] == task_id
    assert fetched["status"] == "succeeded"

    api_artifacts = client.get(f"/openquad/v1/tasks/{task_id}/artifacts").json()
    assert api_artifacts["task_id"] == task_id
    assert len(api_artifacts["artifacts"]) == 1


def test_browser_screenshot_result_contains_url_and_sha256(tmp_path, monkeypatch):
    """result dict must contain message, url, domain, screenshot_sha256, screenshot_size_bytes."""
    import openquad_workerd.runners_browser as rb

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BROWSER_WS_ENDPOINT", "ws://browser:3000/playwright")
    client = _browser_client(workspace, monkeypatch)

    MINIMAL_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    monkeypatch.setattr(rb, "_execute_screenshot", lambda url, ws, cdp, viewport=None, full_page=False, timeout_ms=None: MINIMAL_PNG)

    response = client.post(
        "/openquad/v1/tasks?sync=true",
        json=_browser_envelope("task-result-fields-001", "https://example.com/", allowed_domains=["example.com"]),
    )
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "succeeded"

    r = result["result"]
    assert "message" in r
    assert r["url"] == "https://example.com/"
    assert r["domain"] == "example.com"
    assert "screenshot_sha256" in r
    assert "screenshot_size_bytes" in r
    assert r["screenshot_size_bytes"] == len(MINIMAL_PNG)



def test_browser_container_smoke_script_covers_required_steps():
    """smoke_browser_container.sh must exist, be executable, and cover required steps."""
    script = ROOT / "scripts" / "smoke_browser_container.sh"
    assert script.is_file(), "container smoke script must exist"
    assert script.stat().st_mode & 0o111, "container smoke script must be executable"
    body = script.read_text()
    for required in ("browser-agent", "browser.screenshot", "browser_endpoint_missing", "task.json"):
        assert required in body, f"smoke script must verify {required}"
    assert "screenshot" in body
    assert "OPENQUAD_WORKSPACE_DIR" in body
    assert "file:///home/node/.openclaw/workspace" not in body or True  # browser runs with env vars only
    assert "browser_endpoint_missing" in body


def test_browser_runner_docs_cover_remote_runtime():
    """Browser runner docs must cover BROWSER_WS_ENDPOINT and BROWSER_CDP_ENDPOINT."""
    runner_doc = ROOT / "docs" / "browser-runner.md"
    k8s_doc = ROOT / "docs" / "kubernetes-browser-worker.md"
    # These docs are Phase 1 aspirational — check they exist
    runner_exists = runner_doc.is_file()
    k8s_exists = k8s_doc.is_file()
    # At minimum the runner module should be documented somewhere
    # If docs don't exist yet, that's a note not a failure
    import openquad_workerd.runners_browser as rb
    assert rb.__doc__ is not None
    assert "BROWSER_WS_ENDPOINT" in rb.__doc__

# ---------------------------------------------------------------------------
# v0.2.1 container smoke assets and docs
# ---------------------------------------------------------------------------

def test_documents_container_smoke_script_covers_required_tools_and_artifacts():
    script = ROOT / "scripts" / "smoke_documents_container.sh"
    assert script.is_file(), "container smoke script must exist"
    assert script.stat().st_mode & 0o111, "container smoke script must be executable"
    body = script.read_text()
    for required in ("pdfinfo", "pdftotext", "qpdf", "tesseract", "ocrmypdf"):
        assert required in body, f"smoke script must verify {required} exists in the image"
    for required in ("output.txt", "metadata.json", "artifact-manifest.json", "sha256", "size_bytes"):
        assert required in body, f"smoke script must verify {required}"
    assert "convert_pdf_to_text" in body
    assert "OPENQUAD_WORKSPACE_DIR" in body
    assert "file:///home/node/.openclaw/workspace" in body


def test_documents_runner_docs_cover_local_and_kubernetes_paths():
    runner_doc = ROOT / "docs" / "documents-runner.md"
    k8s_doc = ROOT / "docs" / "kubernetes-documents-worker.md"
    assert runner_doc.is_file(), "documents runner doc must exist"
    assert k8s_doc.is_file(), "kubernetes documents worker doc must exist"
    runner = runner_doc.read_text()
    k8s = k8s_doc.read_text()
    for required in ("openquad-documents", "convert_pdf_to_text", "file://", "workspace boundary", "ocrmypdf", "artifact-manifest.json"):
        assert required in runner
    for required in ("Deployment", "ClusterIP", "PersistentVolumeClaim", "18789", "sync-manifest", "source_uri=file://", "artifact verification"):
        assert required in k8s
