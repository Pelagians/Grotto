#!/usr/bin/env python3
"""Thin OpenAdapt attachment worker for a Nereus-authorized Teach session.

The adapter owns no automation semantics. It connects upstream OpenAdapt Flow
to a caller-owned browser page, delegates recording and compilation to Flow,
and emits bounded provenance evidence. Browser composition and lifecycle stay
with ``web-apps``; authority and artifact custody stay with Nereus.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping
from urllib.parse import urlparse
import zipfile


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} must be a non-empty object")
    return dict(value)


@dataclass(frozen=True)
class TeachAttachConfig:
    teach_session_id: str
    cdp_url: str
    start_url: str
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


class AttachedInteractiveRecorder:
    """Reuse Flow's recorder pump while replacing only browser attachment."""

    def __init__(self, config: TeachAttachConfig) -> None:
        self.config = config
        from openadapt_flow.interactive_recorder import InteractiveRecorder

        stop_when = (
            None
            if config.stop_file is None
            else lambda: config.stop_file is not None and config.stop_file.is_file()
        )
        self._inner = InteractiveRecorder(
            config.start_url,
            config.source_dir,
            secret_fields=config.secret_fields,
            param_fields=config.param_fields,
            identifier_fields=config.identifier_fields,
            headless=False,
            stop_when=stop_when,
        )
        self._pw = None
        self._browser = None

    @property
    def page(self):
        return self._inner.page

    def start(self) -> None:
        from openadapt_flow.backends.playwright_backend import PlaywrightBackend
        from openadapt_flow.interactive_recorder import _INIT_JS, _SPECIAL_KEYS
        from openadapt_flow.recorder import Recorder
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.config.cdp_url)
            if len(self._browser.contexts) != 1:
                raise RuntimeError("Teach CDP browser must expose exactly one context")
            context = self._browser.contexts[0]
            if len(context.pages) != 1:
                raise RuntimeError("Teach CDP context must expose exactly one page")
            page = context.pages[0]
            self._inner.page = page
            page.on("close", lambda _=None: setattr(self._inner, "done", True))
            page.expose_binding(
                "__oaflow_emit",
                lambda source, detail: self._inner._pyq.append(detail),
            )
            init_js = (
                _INIT_JS.replace(
                    "__SECRET_NAMES__", json.dumps(sorted(self.config.secret_fields))
                )
                .replace(
                    "__IDENT_NAMES__", json.dumps(sorted(self.config.identifier_fields))
                )
                .replace("__SPECIAL_KEYS__", json.dumps(list(_SPECIAL_KEYS)))
            )
            # Future documents and the already-loaded document both need the
            # recorder before the human interaction gate is opened.
            page.add_init_script(init_js)
            page.evaluate(init_js)
            if page.url != self.config.start_url:
                page.goto(self.config.start_url)
                try:
                    page.wait_for_load_state("load")
                except Exception:
                    pass
            self._inner.backend = PlaywrightBackend(page)
            self._inner.recorder = Recorder(
                self._inner.backend,
                self.config.source_dir,
                app_url=self.config.start_url,
                system_of_record_reader=self._inner._system_of_record_reader,
                **self._inner._settle,
            )
            self._inner._last_frame = self._inner.recorder._wait_settled()
            self._inner._last_structural = self._inner._structural_state()
            if self.config.ready_file is not None:
                self.config.ready_file.parent.mkdir(parents=True, exist_ok=True)
                self.config.ready_file.write_text("ready\n", encoding="utf-8")
        except Exception:
            self._disconnect()
            raise

    def run(self) -> Path:
        print(
            f"Recording {self.config.start_url}\n"
            "  The existing browser is instrumented; open the authorized "
            "Selkies session to demonstrate the task."
        )
        try:
            while not self._inner.done:
                if not self._inner.pump():
                    break
        except KeyboardInterrupt:
            print("\n[record] stopping")
        return self.finish()

    def finish(self) -> Path:
        try:
            self._inner._flush_type()
            self._inner._flush_scroll()
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
    _assert_ui_only(workflow)
    schema_version = workflow.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError("compiled workflow has no integer schema_version")
    return {
        "outcome": "compiled",
        "actuation_class": "ui_only",
        "bundle_schema_version": str(schema_version),
        "model_grounding_enabled": False,
        "effect_verification_authority": False,
        "promotion_authority": False,
        "execution_authority": False,
    }


def archive_native_directory(source_dir: Path, output_path: Path) -> dict[str, Any]:
    """Create stable opaque bytes without interpreting OpenAdapt internals."""
    if not source_dir.is_dir():
        raise ValueError("native artifact source directory does not exist")
    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError("native artifact directory is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            if path.is_symlink():
                raise ValueError("native artifact directories may not contain symlinks")
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, path.read_bytes())
    content = output_path.read_bytes()
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
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
    else:
        print(
            json.dumps(
                archive_native_directory(args.source, args.output), sort_keys=True
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
