"""browser.screenshot / screenshot runner.

Connects to a remote browser runtime via BROWSER_WS_ENDPOINT (Playwright WebSocket
protocol) or BROWSER_CDP_ENDPOINT (Chrome DevTools Protocol), navigates to the
requested URL, and captures a PNG screenshot.

Phase 1 targets the vic-web headless runtime — the worker stays thin and does NOT
launch its own browser instance.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .artifacts import artifact_from_file, write_artifact_manifest
from .contracts import Artifact, TaskEnvelope, TaskError, TaskResult
from .events import append_event
from .manifest import worker_name
from .task_store import prepare_task_dir


def _validate_and_resolve(url: str, allowed_domains: list[str]) -> str:
    """Validate URL scheme and check domain against allowed_domains constraint.

    Returns the extracted domain for logging.
    Raises ValueError on any validation failure.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Only http/https URLs are supported for screenshots; got '{parsed.scheme}'"
        )

    domain = parsed.hostname or ""
    if not domain:
        raise ValueError("URL must have a valid hostname")

    if allowed_domains:
        if not any(
            domain == allowed or domain.endswith(f".{allowed}")
            for allowed in allowed_domains
        ):
            raise ValueError(
                f"Domain '{domain}' is not in allowed_domains: {allowed_domains}. "
                "All requests must be within the allowed domain list."
            )

    return domain


def _execute_screenshot(
    url: str,
    browser_ws_endpoint: str | None,
    browser_cdp_endpoint: str | None,
    viewport: dict | None = None,
    full_page: bool = False,
    timeout_ms: int = 30000,
) -> bytes:
    """Take a screenshot using Playwright.  Returns raw PNG bytes.

    This function is designed to be monkeypatchable in tests — tests can replace it
    with a function that returns a fake or minimal PNG without a real browser.

    Raises TimeoutError on navigation timeout, RuntimeError on missing endpoint,
    and other Playwright exceptions on screenshot or connection failures.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
    except ImportError:  # pragma: no cover — playwright not installed
        PlaywrightTimeout = TimeoutError  # type: ignore[assignment]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if browser_ws_endpoint:
            browser = p.chromium.connect(browser_ws_endpoint)
        elif browser_cdp_endpoint:
            browser = p.chromium.connect_over_cdp(browser_cdp_endpoint)
        else:
            raise RuntimeError("neither BROWSER_WS_ENDPOINT nor BROWSER_CDP_ENDPOINT is available")

        try:
            if viewport:
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
            else:
                page = browser.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                raise TimeoutError(f"Navigation to {url} timed out after {timeout_ms // 1000}s")

            png = page.screenshot(full_page=full_page)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return png


def run_screenshot(envelope: TaskEnvelope, manifest: dict[str, Any]) -> TaskResult:
    """browser.screenshot / screenshot runner.

    Takes a screenshot of the specified URL using a remote Playwright or CDP
    browser runtime.
    """
    worker = worker_name(manifest)
    task_id = envelope.task_id
    errors: list[TaskError] = []
    artifacts_list: list[Artifact] = []

    # -- Extract input ---------------------------------------------------------------
    url = envelope.input.get("url", "")
    if not url:
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": "url is required in task input for screenshot"},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(code="missing_input", message="url is required in task input")],
        )

    allowed_domains = envelope.constraints.allowed_domains
    viewport = envelope.input.get("viewport")
    full_page = envelope.input.get("full_page", False)

    # -- Validate URL and domain constraints ----------------------------------------
    try:
        domain = _validate_and_resolve(url, allowed_domains)
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
            errors=[TaskError(code="invalid_url", message=str(exc))],
        )

    # -- Check that a browser runtime is reachable -----------------------------------
    browser_ws = os.environ.get("BROWSER_WS_ENDPOINT") or None
    browser_cdp = os.environ.get("BROWSER_CDP_ENDPOINT") or None
    if not browser_ws and not browser_cdp:
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={
                "message": "No browser runtime endpoint configured. "
                "Set BROWSER_WS_ENDPOINT or BROWSER_CDP_ENDPOINT in the worker environment.",
            },
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[
                TaskError(
                    code="browser_endpoint_missing",
                    message="BROWSER_WS_ENDPOINT or BROWSER_CDP_ENDPOINT is required",
                )
            ],
        )

    # -- Prepare task artifact directory --------------------------------------------
    tdir = prepare_task_dir(task_id)
    artifact_dir = tdir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # -- Clamp viewport -------------------------------------------------------------
    MAX_VIEWPORT = (3840, 2160)
    if viewport:
        vw = viewport.get("width", 1920)
        vh = viewport.get("height", 1080)
        if vw > MAX_VIEWPORT[0] or vh > MAX_VIEWPORT[1]:
            return TaskResult(
                task_id=task_id,
                status="failed",
                worker=worker,
                capability=envelope.capability,
                task_type=envelope.task_type,
                result={
                    "message": f"Viewport {vw}x{vh} exceeds maximum {MAX_VIEWPORT[0]}x{MAX_VIEWPORT[1]}",
                },
                policy_decision=envelope.policy,
                provenance=envelope.provenance,
                errors=[TaskError(
                    code="viewport_too_large",
                    message=f"Viewport dimensions {vw}x{vh} exceed maximum {MAX_VIEWPORT[0]}x{MAX_VIEWPORT[1]}",
                    details={"width": vw, "height": vh, "max_width": MAX_VIEWPORT[0], "max_height": MAX_VIEWPORT[1]},
                )],
            )

    # -- Determine timeout ----------------------------------------------------------
    timeout_ms = (envelope.constraints.max_runtime_seconds or 30) * 1000

    # -- Take the screenshot --------------------------------------------------------
    append_event(
        task_id, "task.tool_start",
        {"tool": "playwright_screenshot", "url": url, "domain": domain, "has_ws": bool(browser_ws)},
    )

    try:
        png_bytes = _execute_screenshot(
            url, browser_ws, browser_cdp,
            viewport=viewport, full_page=full_page,
            timeout_ms=timeout_ms,
        )
    except TimeoutError:
        msg = f"Screenshot navigation timed out after {timeout_ms // 1000}s for {url}"
        errors.append(TaskError(code="navigation_timeout", message=msg, details={"url": url, "timeout_ms": timeout_ms}))
        append_event(task_id, "task.tool_error", {"tool": "playwright_screenshot", "error": msg})
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": msg, "url": url},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=errors,
        )
    except Exception as exc:
        code = "screenshot_failed"
        msg = f"Screenshot failed: {type(exc).__name__}: {exc}"
        errors.append(TaskError(code=code, message=msg, details={"url": url}))
        append_event(task_id, "task.tool_error", {"tool": "playwright_screenshot", "error": msg})
        return TaskResult(
            task_id=task_id,
            status="failed",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": msg, "url": url},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=errors,
        )

    append_event(task_id, "task.tool_done", {"tool": "playwright_screenshot", "size": len(png_bytes)})

    # -- Write PNG artifact ---------------------------------------------------------
    png_path = artifact_dir / "screenshot.png"
    png_path.write_bytes(png_bytes)

    artifact = artifact_from_file(png_path, kind="png", content_type="image/png")
    artifacts_list.append(artifact)
    write_artifact_manifest(task_id, artifacts_list)
    append_event(
        task_id, "task.artifact_written",
        {"kind": "png", "sha256": artifact.sha256, "size_bytes": artifact.size_bytes},
    )

    # -- Build succeeded result -----------------------------------------------------
    return TaskResult(
        task_id=task_id,
        status="succeeded",
        worker=worker,
        capability=envelope.capability,
        task_type=envelope.task_type,
        result={
            "message": "Screenshot captured successfully",
            "url": url,
            "domain": domain,
            "screenshot_sha256": artifact.sha256,
            "screenshot_size_bytes": artifact.size_bytes,
        },
        policy_decision=envelope.policy,
        provenance=envelope.provenance,
        artifacts=artifacts_list,
        errors=errors,
    )
