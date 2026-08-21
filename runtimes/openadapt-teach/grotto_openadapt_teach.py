#!/usr/bin/env python3
"""Thin OpenAdapt attachment worker for a Nereus-authorized Teach session.

The adapter owns no automation semantics. It connects upstream OpenAdapt Flow
to a caller-owned browser context, delegates recording and compilation to Flow,
and emits bounded provenance evidence. Browser composition and lifecycle stay
with ``web-apps``; authority and artifact custody stay with Nereus.

Two properties are load-bearing and are enforced here rather than documented:

Passive recording
    The adapter never navigates, clicks, types, reloads, or otherwise drives
    the browser. Loopback CDP is exposure containment, not an authorization
    boundary -- an attached worker holds full browser-session authority -- so
    the restraint has to be visible in the code and checked by a policy test.

Context-scoped instrumentation
    Recording is installed on the browser *context*, not a single page, so
    pages created after recording begins (popups, target=_blank, window.open)
    and their frames are covered instead of silently dropped.

Every private OpenAdapt dependency lives in ``openadapt_compat``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any, Mapping
from urllib.parse import urlparse
import zipfile

try:
    from openadapt_compat import (
        EVENT_BINDING_NAME,
        CompatibilityError,
        attach_inner_recorder,
        build_inner_recorder,
        emit_event,
        flush_pending,
        prime_settled_state,
        probe,
        render_init_script,
        require_compatible,
    )
except ImportError:  # pragma: no cover - exercised only outside the image
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from openadapt_compat import (  # type: ignore[no-redef]
        EVENT_BINDING_NAME,
        CompatibilityError,
        attach_inner_recorder,
        build_inner_recorder,
        emit_event,
        flush_pending,
        prime_settled_state,
        probe,
        render_init_script,
        require_compatible,
    )


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Bundle schema versions this adapter has actually been read against. An
# unknown schema is not "probably fine": the UI-only walk below keys on field
# names that a new schema may have renamed, so an unrecognised version means
# the check silently stops checking.
_SUPPORTED_BUNDLE_SCHEMA_VERSIONS = frozenset({2})

# Streaming bounds. Screenshot-heavy recordings are large; nothing here may
# depend on holding a whole artifact in memory.
_STREAM_CHUNK_BYTES = 1024 * 1024
_DEFAULT_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} must be a non-empty object")
    return dict(value)


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"expected an absolute origin, got {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class TeachAttachConfig:
    teach_session_id: str
    cdp_url: str
    start_url: str
    allowed_origins: tuple[str, ...]
    source_dir: Path
    engine_release: dict[str, Any]
    browser_runtime_release: dict[str, Any]
    adapter_release: dict[str, Any]
    actuation_class: str
    secret_fields: tuple[str, ...] = ()
    param_fields: tuple[str, ...] = ()
    identifier_fields: tuple[str, ...] = ()
    stop_file: Path | None = None
    ready_file: Path | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TeachAttachConfig":
        session_id = raw.get("teach_session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("teach_session_id must be a non-empty string")

        cdp_url = raw.get("cdp_url")
        if not isinstance(cdp_url, str):
            raise ValueError("cdp_url must be a string")
        parsed = urlparse(cdp_url)
        if parsed.scheme not in {"http", "https", "ws", "wss"}:
            raise ValueError("cdp_url must use HTTP(S) or WebSocket CDP")
        if parsed.hostname not in _LOOPBACK_HOSTS:
            raise ValueError("Teach browser CDP must be loopback-only")

        if raw.get("actuation_class") != "ui_only":
            raise ValueError("the Teach worker accepts only actuation_class=ui_only")

        start_url = raw.get("start_url")
        if not isinstance(start_url, str) or not start_url:
            raise ValueError("start_url must be a non-empty string")
        source_dir = raw.get("source_dir")
        if not isinstance(source_dir, str) or not source_dir:
            raise ValueError("source_dir must be a non-empty string")

        # The server decides which origins a Teach session may observe. The
        # adapter cannot navigate, so this is an assertion about where the
        # caller-owned browser already is, not a navigation instruction.
        raw_origins = raw.get("allowed_origins")
        if (
            not isinstance(raw_origins, list)
            or not raw_origins
            or not all(isinstance(item, str) and item for item in raw_origins)
        ):
            raise ValueError("allowed_origins must be a non-empty list of origins")
        try:
            origins = tuple(sorted({_origin(item) for item in raw_origins}))
        except ValueError as error:
            raise ValueError(f"allowed_origins entry is not an origin: {error}") from error
        if _origin(start_url) not in origins:
            raise ValueError("start_url origin is not inside allowed_origins")

        def names(field: str) -> tuple[str, ...]:
            value = raw.get(field, [])
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise ValueError(f"{field} must be a list of non-empty strings")
            return tuple(value)

        stop_file_raw = raw.get("stop_file")
        if stop_file_raw is not None and (
            not isinstance(stop_file_raw, str) or not stop_file_raw
        ):
            raise ValueError("stop_file must be a non-empty string when present")
        ready_file_raw = raw.get("ready_file")
        if ready_file_raw is not None and (
            not isinstance(ready_file_raw, str) or not ready_file_raw
        ):
            raise ValueError("ready_file must be a non-empty string when present")

        return cls(
            teach_session_id=session_id,
            cdp_url=cdp_url,
            start_url=start_url,
            allowed_origins=origins,
            source_dir=Path(source_dir),
            engine_release=_required_mapping(raw.get("engine_release"), "engine_release"),
            browser_runtime_release=_required_mapping(
                raw.get("browser_runtime_release"), "browser_runtime_release"
            ),
            adapter_release=_required_mapping(
                raw.get("adapter_release"), "adapter_release"
            ),
            actuation_class="ui_only",
            secret_fields=names("secret_fields"),
            param_fields=names("param_fields"),
            identifier_fields=names("identifier_fields"),
            stop_file=None if stop_file_raw is None else Path(stop_file_raw),
            ready_file=None if ready_file_raw is None else Path(ready_file_raw),
        )

    def permits(self, url: str) -> bool:
        try:
            return _origin(url) in self.allowed_origins
        except ValueError:
            # about:blank and friends carry no origin and no observable data.
            return False


class AttachedInteractiveRecorder:
    """Attach Flow to a caller-owned browser context. Never drive it."""

    def __init__(self, config: TeachAttachConfig) -> None:
        self.config = config
        self.instrumented_frames = 0
        self.instrumented_pages = 0
        self.late_pages = 0
        self.rejected_events = 0
        self._inner = None
        self._pw = None
        self._browser = None
        self._context = None

    @property
    def page(self):
        return None if self._inner is None else self._inner.page

    def _stop_when(self):
        stop_file = self.config.stop_file
        if stop_file is None:
            return None
        return lambda: stop_file.is_file()

    def _instrument_page(self, page, *, late: bool) -> None:
        """Install the recorder in every already-loaded frame of one page.

        Future documents are covered by the context-level init script; this
        covers documents that already exist at attach time, which the init
        script by definition cannot reach.
        """
        self.instrumented_pages += 1
        if late:
            self.late_pages += 1
        page.on("close", self._on_page_closed)
        for frame in page.frames:
            try:
                frame.evaluate(self._init_js)
                self.instrumented_frames += 1
            except Exception:
                # A frame can be mid-navigation or cross-origin-detached. The
                # context init script still covers its next document, so a
                # miss here is recoverable and must not abort attachment.
                continue

    def _on_page_closed(self, page=None) -> None:
        if self._context is None or self._inner is None:
            return
        if not self._context.pages:
            self._inner.done = True

    def _on_new_page(self, page) -> None:
        """A popup or window.open target appeared after recording began."""
        if not self.config.permits(page.url):
            # Do not close it: web-apps owns lifecycle and the human may have
            # opened it deliberately. Record that it was not instrumented.
            print(
                json.dumps(
                    {
                        "event": "page_outside_allowed_origins",
                        "instrumented": False,
                    }
                ),
                flush=True,
            )
            return
        self._instrument_page(page, late=True)

    def _on_event(self, source, detail) -> None:
        """Accept an event only if its current source document is authorized.

        A page may navigate after attachment, and an allowed page may contain
        a cross-origin frame. The binding source is therefore authoritative at
        event intake. Prefer its frame: falling back to the allowed top-level
        page would launder an event emitted by a disallowed child document.
        """
        def source_value(name: str):
            if isinstance(source, Mapping):
                return source.get(name)
            return getattr(source, name, None)

        frame = source_value("frame")
        page = source_value("page")
        source_object = frame if frame is not None else page
        source_kind = "frame" if frame is not None else "page"
        source_url = getattr(source_object, "url", None)
        if not isinstance(source_url, str) or not self.config.permits(source_url):
            self.rejected_events += 1
            print(
                json.dumps(
                    {
                        "event": "event_outside_allowed_origins",
                        "accepted": False,
                        "source_kind": source_kind,
                        "rejected_events": self.rejected_events,
                    }
                ),
                flush=True,
            )
            return
        emit_event(self._inner, detail)

    def start(self) -> None:
        require_compatible()
        from playwright.sync_api import sync_playwright

        self._inner = build_inner_recorder(
            start_url=self.config.start_url,
            source_dir=self.config.source_dir,
            secret_fields=self.config.secret_fields,
            param_fields=self.config.param_fields,
            identifier_fields=self.config.identifier_fields,
            stop_when=self._stop_when(),
        )
        self._init_js = render_init_script(
            secret_fields=self.config.secret_fields,
            identifier_fields=self.config.identifier_fields,
        )

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.config.cdp_url)
            if len(self._browser.contexts) != 1:
                raise RuntimeError("Teach CDP browser must expose exactly one context")
            context = self._browser.contexts[0]
            self._context = context
            if not context.pages:
                raise RuntimeError("Teach CDP context exposes no page to observe")

            # The adapter has no navigation authority, so the browser must
            # already be somewhere the server authorized. Refuse rather than
            # steer: steering is exactly the authority this worker must not
            # hold.
            for page in context.pages:
                if not self.config.permits(page.url):
                    raise RuntimeError(
                        "caller-owned browser is outside the authorized Teach origins"
                    )

            # Context scope, not page scope: this is what makes popups and
            # later-created pages recordable at all.
            context.expose_binding(
                EVENT_BINDING_NAME,
                self._on_event,
            )
            context.add_init_script(self._init_js)
            context.on("page", self._on_new_page)
            for page in context.pages:
                self._instrument_page(page, late=False)

            primary = context.pages[0]
            attach_inner_recorder(
                self._inner,
                page=primary,
                source_dir=self.config.source_dir,
                start_url=self.config.start_url,
            )
            prime_settled_state(self._inner)
            if self.config.ready_file is not None:
                self.config.ready_file.parent.mkdir(parents=True, exist_ok=True)
                self.config.ready_file.write_text("ready\n", encoding="utf-8")
        except Exception:
            self._disconnect()
            raise

    def run(self) -> Path:
        print(
            json.dumps(
                {
                    "event": "recording_started",
                    "teach_session_id": self.config.teach_session_id,
                    # The start URL may carry identifiers or a session token;
                    # its digest is enough to correlate with Nereus.
                    "start_url_sha256": hashlib.sha256(
                        self.config.start_url.encode("utf-8")
                    ).hexdigest(),
                    "instrumented_pages": self.instrumented_pages,
                    "instrumented_frames": self.instrumented_frames,
                }
            ),
            flush=True,
        )
        try:
            while not self._inner.done:
                if not self._inner.pump():
                    break
        except KeyboardInterrupt:
            print(json.dumps({"event": "recording_interrupted"}), flush=True)
        return self.finish()

    def finish(self) -> Path:
        try:
            flush_pending(self._inner)
            if self._inner.recorder is None:
                raise RuntimeError("Teach recorder was not started")
            return self._inner.recorder.finish()
        finally:
            # Never call Browser.close(): web-apps owns the browser lifecycle.
            self._disconnect()

    def _disconnect(self) -> None:
        if self._pw is not None:
            self._pw.stop()
            self._pw = None


def _assert_ui_only(value: Any, *, path: str = "workflow") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "api_binding" and child not in (None, {}, []):
                raise ValueError(f"compiled bundle crosses UI actuation at {child_path}")
            if key in {"actuation_class", "actuator_kind"} and child not in (
                None,
                "ui",
                "ui_only",
                "browser",
                "web",
            ):
                raise ValueError(f"compiled bundle is not UI-only at {child_path}")
            _assert_ui_only(child, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_ui_only(child, path=f"{path}[{index}]")


def compile_native_bundle(
    source_dir: Path, decisions_path: Path, bundle_dir: Path
) -> dict[str, Any]:
    """Compile through Flow and return bounded evidence, never a Teach IR."""
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    allowed = {"workflow_name", "param_overrides", "secret_param_steps"}
    unexpected = set(decisions) - allowed
    if unexpected:
        raise ValueError(f"unsupported human decision fields: {sorted(unexpected)}")
    name = decisions.get("workflow_name")
    if not isinstance(name, str) or not name:
        raise ValueError("workflow_name decision is required")

    from openadapt_flow.compiler.compile import compile_recording

    compile_recording(
        source_dir,
        bundle_dir,
        name=name,
        param_overrides=decisions.get("param_overrides") or {},
        secret_param_steps=decisions.get("secret_param_steps") or [],
        annotate=False,
        mine_effects=False,
        target_surface="web",
    )
    workflow_path = bundle_dir / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    schema_version = workflow.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError("compiled workflow has no integer schema_version")
    if schema_version not in _SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise ValueError(
            f"compiled bundle schema version {schema_version} is unrecognised; "
            "the UI-only structural check has not been read against it"
        )
    _assert_ui_only(workflow)
    return {
        "outcome": "compiled",
        "actuation_class": "ui_only",
        "bundle_schema_version": str(schema_version),
        "model_grounding_enabled": False,
        "effect_verification_authority": False,
        "promotion_authority": False,
        "execution_authority": False,
        # Worker evidence, never qualification. Nereus re-derives UI-only from
        # the artifact it holds custody of before anything is admitted.
        "ui_only_check": "structural_workflow_json_only",
    }


def archive_native_directory(
    source_dir: Path,
    output_path: Path,
    *,
    max_bytes: int = _DEFAULT_MAX_ARCHIVE_BYTES,
) -> dict[str, Any]:
    """Create stable opaque bytes without interpreting OpenAdapt internals.

    Streamed in both directions: screenshot-heavy recordings routinely exceed
    what a worker pod should hold in memory, and the size ceiling is checked
    while writing rather than after.
    """
    if not source_dir.is_dir():
        raise ValueError("native artifact source directory does not exist")
    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError("native artifact directory is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            if path.is_symlink():
                raise ValueError("native artifact directories may not contain symlinks")
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            with path.open("rb") as source, archive.open(info, "w") as sink:
                while True:
                    chunk = source.read(_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError(
                            "native artifact directory exceeds the archive size limit"
                        )
                    sink.write(chunk)
    digest = hashlib.sha256()
    size = 0
    with output_path.open("rb") as handle:
        while True:
            chunk = handle.read(_STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return {
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "media_type": "application/zip",
        "archive_format": "deterministic-zip-v1",
    }


def _read_config(path: Path) -> TeachAttachConfig:
    return TeachAttachConfig.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--config", type=Path, required=True)
    compile_command = subparsers.add_parser("compile")
    compile_command.add_argument("--source", type=Path, required=True)
    compile_command.add_argument("--decisions", type=Path, required=True)
    compile_command.add_argument("--bundle", type=Path, required=True)
    archive_command = subparsers.add_parser("archive")
    archive_command.add_argument("--source", type=Path, required=True)
    archive_command.add_argument("--output", type=Path, required=True)
    archive_command.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_ARCHIVE_BYTES
    )
    subparsers.add_parser(
        "canary", help="report the installed OpenAdapt private-API compatibility"
    )

    args = parser.parse_args(argv)
    if args.command == "record":
        recorder = AttachedInteractiveRecorder(_read_config(args.config))
        recorder.start()
        out = recorder.run()
        print(json.dumps({"outcome": "recorded", "source_dir": str(out)}))
    elif args.command == "compile":
        print(
            json.dumps(
                compile_native_bundle(args.source, args.decisions, args.bundle),
                sort_keys=True,
            )
        )
    elif args.command == "canary":
        report = probe()
        print(json.dumps(report.as_json(), sort_keys=True, indent=2))
        if not report.ok:
            raise CompatibilityError("OpenAdapt private-API canary failed")
    else:
        print(
            json.dumps(
                archive_native_directory(
                    args.source, args.output, max_bytes=args.max_bytes
                ),
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
