"""documents.convert / convert_pdf_to_text runner.

Deterministic tools only in this first slice:
  1. pdfinfo  – gather page count, title, metadata
  2. pdftotext – extract selectable text
  3. qpdf     – fallback linearize/decrypt if pdftotext yields nothing
  4. ocrmypdf / tesseract – fallback OCR if available and text still empty

The runner:
  - validates source_uri is a file:// URI inside the allowed workspace
  - writes full extracted text as a text artifact with sha256 + size_bytes
  - writes a JSON metadata artifact
  - updates the artifact manifest
  - records granular events
  - fails clearly if required tools or source files are missing
  - never returns succeeded with empty or fake text
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .contracts import Artifact, ArtifactKind, TaskEnvelope, TaskError, TaskResult
from .artifacts import artifact_from_file, write_artifact_manifest
from .events import append_event
from .manifest import worker_name
from .task_store import prepare_task_dir, task_dir, write_json, result_path, task_path


# ---------------------------------------------------------------------------
# Workspace boundary helpers
# ---------------------------------------------------------------------------

def _workspace_root() -> Path:
    """Return the resolved allowed input root for source documents."""
    root = os.getenv("OPENQUAD_WORKSPACE_DIR") or os.getenv("DOCUMENT_INPUT_ROOT")
    if root:
        return Path(root).resolve()
    # Default: the workspace directory used by the task store
    from .task_store import workspace_dir
    return workspace_dir().resolve()


def _resolve_source_uri(source_uri: str, workspace_root: Path) -> Path:
    """Resolve a file:// URI to a Path, enforcing workspace boundary.

    Raises ValueError with a user-safe message on any violation.
    """
    parsed = urlparse(source_uri)
    if parsed.scheme != "file":
        raise ValueError(
            f"source_uri must use the file:// scheme; got '{parsed.scheme}://'"
        )
    raw_path = parsed.path
    if not raw_path:
        raise ValueError("source_uri file:// path is empty")

    # Resolve without requiring existence yet (strict=False so we can give a better error)
    candidate = Path(raw_path).resolve(strict=False)

    # Path-traversal boundary check
    if candidate != workspace_root and workspace_root not in candidate.parents:
        raise ValueError(
            f"source_uri resolves outside the allowed workspace. "
            f"Path '{candidate}' is not under '{workspace_root}'. "
            f"Mount source documents into the workspace directory."
        )

    return candidate


# ---------------------------------------------------------------------------
# Tool availability
# ---------------------------------------------------------------------------

def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _require_tool(name: str) -> None:
    if not _tool_available(name):
        raise RuntimeError(f"Required tool '{name}' is not installed or not on PATH.")


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _pdfinfo(source_path: Path) -> dict[str, Any]:
    """Run pdfinfo and return parsed key-value metadata."""
    if not _tool_available("pdfinfo"):
        return {"error": "pdfinfo not available"}
    try:
        result = _run(["pdfinfo", str(source_path)])
        meta: dict[str, Any] = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        if result.returncode != 0:
            meta["_pdfinfo_error"] = result.stderr.strip()
        return meta
    except Exception as exc:
        return {"error": str(exc)}


def _pdftotext(source_path: Path, output_path: Path) -> tuple[bool, str]:
    """Run pdftotext. Returns (success, error_message)."""
    if not _tool_available("pdftotext"):
        return False, "pdftotext not available"
    try:
        result = _run(["pdftotext", "-layout", str(source_path), str(output_path)])
        if result.returncode != 0:
            return False, result.stderr.strip() or f"pdftotext exit {result.returncode}"
        if not output_path.exists() or output_path.stat().st_size == 0:
            return False, "pdftotext produced empty output"
        # Check if output is just whitespace
        text = output_path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return False, "pdftotext output contains only whitespace (likely image-only PDF)"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "pdftotext timed out"
    except Exception as exc:
        return False, str(exc)


def _qpdf_linearize(source_path: Path, out_path: Path) -> tuple[bool, str]:
    """Attempt qpdf linearization (useful for encrypted/malformed PDFs)."""
    if not _tool_available("qpdf"):
        return False, "qpdf not available"
    try:
        result = _run(["qpdf", "--linearize", str(source_path), str(out_path)])
        if result.returncode != 0:
            return False, result.stderr.strip() or f"qpdf exit {result.returncode}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "qpdf timed out"
    except Exception as exc:
        return False, str(exc)


def _ocrmypdf(source_path: Path, output_pdf_path: Path, txt_path: Path, language: str = "eng") -> tuple[bool, str]:
    """Run ocrmypdf with --sidecar to produce a text sidecar file."""
    if not _tool_available("ocrmypdf"):
        return False, "ocrmypdf not available"
    try:
        result = _run(
            [
                "ocrmypdf",
                "--sidecar", str(txt_path),
                "--language", language,
                "--skip-text",          # skip pages that already have selectable text
                "--output-type", "pdf",
                str(source_path),
                str(output_pdf_path),
            ],
            timeout=300,
        )
        if result.returncode not in (0, 6):  # 6 = already has text (success for us)
            return False, result.stderr.strip() or f"ocrmypdf exit {result.returncode}"
        if not txt_path.exists() or txt_path.stat().st_size == 0:
            return False, "ocrmypdf sidecar is empty"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "ocrmypdf timed out"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Main runner function
# ---------------------------------------------------------------------------

def run_convert_pdf_to_text(envelope: TaskEnvelope, manifest: dict[str, Any]) -> TaskResult:
    """Real convert_pdf_to_text runner using deterministic tools."""

    worker = worker_name(manifest)
    task_id = envelope.task_id
    errors: list[TaskError] = []
    evidence: list[dict[str, Any]] = []
    artifacts: list[Artifact] = []

    # -- Resolve source URI ---------------------------------------------------
    source_uri = envelope.input.get("source_uri", "")
    if not source_uri:
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": "source_uri is required in task input"},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="missing_input", message="source_uri is required in task input")],
        )

    workspace_root = _workspace_root()

    try:
        source_path = _resolve_source_uri(source_uri, workspace_root)
    except ValueError as exc:
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": str(exc)},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="invalid_source_uri", message=str(exc))],
        )

    # -- Check source file exists ---------------------------------------------
    if not source_path.exists():
        msg = f"Source file not found: {source_path}"
        append_event(task_id, "task.tool_error", {"tool": "file_check", "error": msg})
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": msg},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="source_not_found", message=msg)],
        )

    if not source_path.is_file():
        msg = f"Source path is not a regular file: {source_path}"
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": msg},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="source_not_file", message=msg)],
        )

    # -- Require at least pdftotext -------------------------------------------
    if not _tool_available("pdftotext"):
        msg = "Required tool 'pdftotext' is not installed. Install poppler-utils."
        append_event(task_id, "task.tool_error", {"tool": "pdftotext", "error": msg})
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": msg},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="tool_not_available", message=msg)],
        )

    # -- Prepare task artifact directory --------------------------------------
    tdir = prepare_task_dir(task_id)
    artifact_dir = tdir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # -- Step 1: pdfinfo (best-effort metadata) --------------------------------
    append_event(task_id, "task.tool_start", {"tool": "pdfinfo"})
    pdf_meta = _pdfinfo(source_path)
    evidence.append({"tool": "pdfinfo", "result": pdf_meta})
    append_event(task_id, "task.tool_done", {"tool": "pdfinfo", "pages": pdf_meta.get("Pages")})

    # -- Step 2: pdftotext ----------------------------------------------------
    txt_path = artifact_dir / "output.txt"
    append_event(task_id, "task.tool_start", {"tool": "pdftotext"})
    ok, err = _pdftotext(source_path, txt_path)
    if not ok:
        errors.append(TaskError(code="pdftotext_failed", message=err))
        evidence.append({"tool": "pdftotext", "ok": False, "error": err})
        append_event(task_id, "task.tool_error", {"tool": "pdftotext", "error": err})

        # -- Step 3: qpdf fallback then retry pdftotext -----------------------
        with tempfile.TemporaryDirectory() as tmpdir:
            linearized_path = Path(tmpdir) / "linearized.pdf"
            append_event(task_id, "task.tool_start", {"tool": "qpdf"})
            qok, qerr = _qpdf_linearize(source_path, linearized_path)
            if qok:
                evidence.append({"tool": "qpdf", "ok": True})
                append_event(task_id, "task.tool_done", {"tool": "qpdf"})
                ok2, err2 = _pdftotext(linearized_path, txt_path)
                if ok2:
                    ok = True
                    errors = [e for e in errors if e.code != "pdftotext_failed"]
                    evidence.append({"tool": "pdftotext_after_qpdf", "ok": True})
                    append_event(task_id, "task.tool_done", {"tool": "pdftotext_after_qpdf"})
                else:
                    errors.append(TaskError(code="pdftotext_after_qpdf_failed", message=err2))
                    evidence.append({"tool": "pdftotext_after_qpdf", "ok": False, "error": err2})
                    append_event(task_id, "task.tool_error", {"tool": "pdftotext_after_qpdf", "error": err2})
            else:
                errors.append(TaskError(code="qpdf_failed", message=qerr))
                evidence.append({"tool": "qpdf", "ok": False, "error": qerr})
                append_event(task_id, "task.tool_error", {"tool": "qpdf", "error": qerr})

        # -- Step 4: ocrmypdf / tesseract fallback ----------------------------
        if not ok:
            ocr_language = os.getenv("OCR_LANGUAGE", "eng")
            ocr_pdf_path = artifact_dir / "ocr-output.pdf"
            ocr_txt_path = artifact_dir / "ocr-output.txt"
            append_event(task_id, "task.tool_start", {"tool": "ocrmypdf"})
            ocrok, ocrerr = _ocrmypdf(source_path, ocr_pdf_path, ocr_txt_path, language=ocr_language)
            if ocrok:
                # Use the sidecar text file as our output artifact
                txt_path = ocr_txt_path
                ok = True
                evidence.append({"tool": "ocrmypdf", "ok": True, "language": ocr_language})
                append_event(task_id, "task.tool_done", {"tool": "ocrmypdf", "language": ocr_language})
                errors = [e for e in errors if e.code in ("pdftotext_failed",)]  # preserve prior errors as informational
            else:
                errors.append(TaskError(code="ocrmypdf_failed", message=ocrerr))
                evidence.append({"tool": "ocrmypdf", "ok": False, "error": ocrerr})
                append_event(task_id, "task.tool_error", {"tool": "ocrmypdf", "error": ocrerr})
    else:
        evidence.append({"tool": "pdftotext", "ok": True})
        append_event(task_id, "task.tool_done", {"tool": "pdftotext"})

    # -- If all tools failed, return a real failure ---------------------------
    if not ok:
        all_error_msgs = "; ".join(e.message for e in errors)
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={
                "message": "All deterministic extraction tools failed. See errors for details.",
                "source_uri": source_uri,
            },
            policy_decision=envelope.policy,
            evidence=evidence,
            provenance=envelope.provenance,
            errors=errors,
        )

    # -- Build text artifact --------------------------------------------------
    text_artifact = artifact_from_file(txt_path, kind="text", content_type="text/plain")
    artifacts.append(text_artifact)

    # -- Build JSON metadata artifact -----------------------------------------
    meta_path = artifact_dir / "metadata.json"
    page_count_raw = pdf_meta.get("Pages", "")
    try:
        page_count = int(page_count_raw)
    except (ValueError, TypeError):
        page_count = None

    metadata_payload = {
        "source_uri": source_uri,
        "source_file": str(source_path),
        "page_count": page_count,
        "pdf_metadata": pdf_meta,
        "text_artifact_sha256": text_artifact.sha256,
        "text_artifact_size_bytes": text_artifact.size_bytes,
        "extraction_tools": [e["tool"] for e in evidence if e.get("ok")],
    }
    write_json(meta_path, metadata_payload)
    meta_artifact = artifact_from_file(meta_path, kind="json", content_type="application/json")
    artifacts.append(meta_artifact)

    # -- Write artifact manifest ----------------------------------------------
    write_artifact_manifest(task_id, artifacts)

    # -- Finalize -------------------------------------------------------------
    result_summary = {
        "message": "PDF text extraction succeeded.",
        "source_uri": source_uri,
        "page_count": page_count,
        "text_size_bytes": text_artifact.size_bytes,
        "text_sha256": text_artifact.sha256,
        "artifact_count": len(artifacts),
    }

    return TaskResult(
        task_id=task_id,
        status="succeeded",
        worker=worker,
        capability=envelope.capability,
        task_type=envelope.task_type,
        result=result_summary,
        policy_decision=envelope.policy,
        evidence=evidence,
        provenance=envelope.provenance,
        artifacts=artifacts,
        errors=errors,  # may contain non-fatal informational errors (e.g. pdftotext initially failed but OCR succeeded)
    )
