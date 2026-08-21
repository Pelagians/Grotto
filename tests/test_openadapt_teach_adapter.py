from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtimes" / "openadapt-teach"
ADAPTER_PATH = RUNTIME_DIR / "grotto_openadapt_teach.py"


def load_adapter():
    if str(RUNTIME_DIR) not in sys.path:
        sys.path.insert(0, str(RUNTIME_DIR))
    spec = importlib.util.spec_from_file_location("grotto_openadapt_teach", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("adapter module is not loadable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeFrame:
    def __init__(
        self,
        name: str,
        *,
        url: str = "http://target:8000/frame",
        raises: bool = False,
    ) -> None:
        self.name = name
        self.url = url
        self.raises = raises
        self.evaluated: list[str] = []

    def evaluate(self, script) -> None:
        if self.raises:
            raise RuntimeError("frame detached")
        self.evaluated.append(script)


class FakePage:
    def __init__(self, url: str = "http://target:8000/", frames=None) -> None:
        self.url = url
        self.frames = frames if frames is not None else [FakeFrame("main")]
        self.handlers: dict[str, object] = {}

    def on(self, event, callback) -> None:
        self.handlers[event] = callback


class FakeContext:
    def __init__(self, pages) -> None:
        self.pages = list(pages)
        self.bindings: list[str] = []
        self.init_scripts: list[str] = []
        self.handlers: dict[str, object] = {}

    def expose_binding(self, name, callback) -> None:
        self.bindings.append(name)
        self.binding_callback = callback

    def add_init_script(self, script) -> None:
        self.init_scripts.append(script)

    def on(self, event, callback) -> None:
        self.handlers[event] = callback

    def open_popup(self, page) -> None:
        """Simulate Chromium announcing a window.open target."""
        self.pages.append(page)
        self.handlers["page"](page)


class FakeBrowser:
    def __init__(self, contexts) -> None:
        self.contexts = contexts
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeChromium:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.endpoints: list[str] = []

    def connect_over_cdp(self, endpoint) -> FakeBrowser:
        self.endpoints.append(endpoint)
        return self.browser


class FakePlaywright:
    def __init__(self, browser) -> None:
        self.chromium = FakeChromium(browser)
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class FakeInnerRecorder:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.done = False
        self.page = None
        self.backend = None
        self.recorder = None
        self.flushed = False
        self.primed = False


class FakeFlowRecorder:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)

    def finish(self) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "meta.json").write_text("{}", encoding="utf-8")
        return self.out_dir


BASE_CONFIG = {
    "teach_session_id": "teach-1",
    "cdp_url": "http://127.0.0.1:9222",
    "start_url": "http://target:8000/task",
    "allowed_origins": ["http://target:8000"],
    "source_dir": "source",
    "engine_release": {"release_id": "openadapt-flow-1.31.0"},
    "browser_runtime_release": {"release_id": "browser-runtime-1"},
    "adapter_release": {"release_id": "grotto-openadapt-teach-1"},
    "actuation_class": "ui_only",
}


def install_compat_fakes(adapter, inner: FakeInnerRecorder, source_dir: Path):
    """Replace only the compatibility seam.

    Every OpenAdapt private dependency is reached through these names, so
    stubbing them is the whole surface: if a future change reaches around
    ``openadapt_compat``, these tests stop covering it and the policy test
    below fails.
    """
    adapter.require_compatible = lambda: None
    adapter.build_inner_recorder = lambda **_kwargs: inner
    adapter.render_init_script = lambda **_kwargs: "INIT_JS"
    adapter.emit_event = lambda target, detail: target.events.append(detail)

    def attach(target, *, page, source_dir, start_url):
        target.page = page
        target.recorder = FakeFlowRecorder(source_dir)
        return target.recorder

    def prime(target) -> None:
        target.primed = True

    def flush(target) -> None:
        target.flushed = True

    adapter.attach_inner_recorder = attach
    adapter.prime_settled_state = prime
    adapter.flush_pending = flush


class ConfigurationTests(unittest.TestCase):
    def test_rejects_non_loopback_cdp_and_non_ui_actuation(self) -> None:
        adapter = load_adapter()
        self.assertEqual(
            adapter.TeachAttachConfig.from_mapping(BASE_CONFIG).actuation_class,
            "ui_only",
        )

        remote = {**BASE_CONFIG, "cdp_url": "http://browser-runtime:9222"}
        with self.assertRaisesRegex(ValueError, "loopback"):
            adapter.TeachAttachConfig.from_mapping(remote)

        api = {**BASE_CONFIG, "actuation_class": "api"}
        with self.assertRaisesRegex(ValueError, "ui_only"):
            adapter.TeachAttachConfig.from_mapping(api)

    def test_requires_server_supplied_allowed_origins(self) -> None:
        adapter = load_adapter()
        missing = {key: value for key, value in BASE_CONFIG.items() if key != "allowed_origins"}
        with self.assertRaisesRegex(ValueError, "allowed_origins"):
            adapter.TeachAttachConfig.from_mapping(missing)

        empty = {**BASE_CONFIG, "allowed_origins": []}
        with self.assertRaisesRegex(ValueError, "allowed_origins"):
            adapter.TeachAttachConfig.from_mapping(empty)

    def test_start_url_must_be_inside_the_authorized_origins(self) -> None:
        adapter = load_adapter()
        escaped = {**BASE_CONFIG, "start_url": "http://elsewhere.internal/task"}
        with self.assertRaisesRegex(ValueError, "allowed_origins"):
            adapter.TeachAttachConfig.from_mapping(escaped)

    def test_origin_membership_ignores_path_and_rejects_opaque_urls(self) -> None:
        adapter = load_adapter()
        config = adapter.TeachAttachConfig.from_mapping(BASE_CONFIG)
        self.assertTrue(config.permits("http://target:8000/deep/path?x=1"))
        self.assertFalse(config.permits("http://target:9999/"))
        self.assertFalse(config.permits("https://target:8000/"))
        self.assertFalse(config.permits("about:blank"))


class AttachmentTests(unittest.TestCase):
    def _start(self, adapter, context, tmp, *, config_overrides=None):
        browser = FakeBrowser([context])
        playwright = FakePlaywright(browser)
        fake_module = types.ModuleType("playwright.sync_api")
        fake_module.sync_playwright = lambda: types.SimpleNamespace(
            start=lambda: playwright
        )
        prior = sys.modules.get("playwright.sync_api")
        sys.modules["playwright.sync_api"] = fake_module

        inner = FakeInnerRecorder()
        install_compat_fakes(adapter, inner, Path(tmp))
        config = adapter.TeachAttachConfig.from_mapping(
            {
                **BASE_CONFIG,
                "source_dir": tmp,
                "ready_file": str(Path(tmp) / "ready"),
                **(config_overrides or {}),
            }
        )
        recorder = adapter.AttachedInteractiveRecorder(config)
        try:
            recorder.start()
        finally:
            if prior is None:
                sys.modules.pop("playwright.sync_api", None)
            else:
                sys.modules["playwright.sync_api"] = prior
        return recorder, inner, browser, playwright

    def test_instrumentation_is_installed_on_the_context_not_a_single_page(self) -> None:
        adapter = load_adapter()
        page = FakePage(frames=[FakeFrame("main"), FakeFrame("iframe")])
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, _inner, browser, playwright = self._start(adapter, context, tmp)

            # Context scope is the whole point: page scope silently drops
            # popups and every page created after recording begins.
            self.assertEqual(context.bindings, [adapter.EVENT_BINDING_NAME])
            self.assertEqual(context.init_scripts, ["INIT_JS"])
            self.assertIn("page", context.handlers)
            self.assertEqual(browser.close_calls, 0)
            self.assertEqual(recorder.instrumented_pages, 1)
            # Both already-attached frames, which the init script cannot reach.
            self.assertEqual(recorder.instrumented_frames, 2)
            for frame in page.frames:
                self.assertEqual(frame.evaluated, ["INIT_JS"])
            del playwright

    def test_pages_created_after_recording_begins_are_instrumented(self) -> None:
        adapter = load_adapter()
        page = FakePage()
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, _inner, _browser, _pw = self._start(adapter, context, tmp)
            self.assertEqual(recorder.late_pages, 0)

            popup = FakePage(
                url="http://target:8000/popup.html",
                frames=[FakeFrame("popup-main"), FakeFrame("popup-child")],
            )
            context.open_popup(popup)

            self.assertEqual(recorder.late_pages, 1)
            self.assertEqual(recorder.instrumented_pages, 2)
            for frame in popup.frames:
                self.assertEqual(frame.evaluated, ["INIT_JS"])

    def test_popup_events_reach_the_recorder_through_the_context_binding(self) -> None:
        adapter = load_adapter()
        context = FakeContext([FakePage()])
        with tempfile.TemporaryDirectory() as tmp:
            _recorder, inner, _browser, _pw = self._start(adapter, context, tmp)
            popup = FakePage(url="http://target:8000/popup.html")
            context.open_popup(popup)
            # A context-scoped binding is shared by every page, so a popup can
            # emit into the same queue as the primary page.
            context.binding_callback(
                types.SimpleNamespace(page=popup),
                {"type": "click", "id": "popup-confirm"},
            )
            self.assertEqual(inner.events, [{"type": "click", "id": "popup-confirm"}])

    def test_later_top_level_navigation_is_checked_at_event_intake(self) -> None:
        adapter = load_adapter()
        page = FakePage()
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, _browser, _pw = self._start(adapter, context, tmp)
            source = types.SimpleNamespace(page=page)

            page.url = "http://target:8000/later"
            context.binding_callback(source, {"id": "allowed-navigation"})
            page.url = "https://outside.example/secret"
            context.binding_callback(source, {"id": "rejected-navigation"})

            self.assertEqual(inner.events, [{"id": "allowed-navigation"}])
            self.assertEqual(recorder.rejected_events, 1)

    def test_existing_cross_origin_iframe_cannot_emit_through_allowed_page(self) -> None:
        adapter = load_adapter()
        allowed = FakeFrame("allowed")
        foreign = FakeFrame("foreign", url="https://outside.example/frame")
        page = FakePage(frames=[allowed, foreign])
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, _browser, _pw = self._start(adapter, context, tmp)

            context.binding_callback(
                types.SimpleNamespace(page=page, frame=allowed), {"id": "allowed-frame"}
            )
            context.binding_callback(
                types.SimpleNamespace(page=page, frame=foreign), {"id": "foreign-frame"}
            )

            self.assertEqual(inner.events, [{"id": "allowed-frame"}])
            self.assertEqual(recorder.rejected_events, 1)

    def test_new_iframe_navigation_is_checked_for_every_event(self) -> None:
        adapter = load_adapter()
        page = FakePage()
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, _browser, _pw = self._start(adapter, context, tmp)
            frame = FakeFrame("new", url="http://target:8000/created")
            source = types.SimpleNamespace(page=page, frame=frame)

            context.binding_callback(source, {"id": "allowed-created-frame"})
            frame.url = "https://outside.example/navigated"
            context.binding_callback(source, {"id": "rejected-created-frame"})

            self.assertEqual(inner.events, [{"id": "allowed-created-frame"}])
            self.assertEqual(recorder.rejected_events, 1)

    def test_about_blank_popup_transitions_are_checked_per_event(self) -> None:
        adapter = load_adapter()
        context = FakeContext([FakePage()])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, _browser, _pw = self._start(adapter, context, tmp)
            popup = FakePage(url="about:blank")
            context.open_popup(popup)
            source = types.SimpleNamespace(page=popup)

            context.binding_callback(source, {"id": "opaque-popup"})
            popup.url = "http://target:8000/popup"
            context.binding_callback(source, {"id": "allowed-popup"})
            popup.url = "https://outside.example/popup"
            context.binding_callback(source, {"id": "rejected-popup"})

            self.assertEqual(inner.events, [{"id": "allowed-popup"}])
            self.assertEqual(recorder.rejected_events, 2)

    def test_rejection_metadata_does_not_echo_url_or_event_detail(self) -> None:
        adapter = load_adapter()
        page = FakePage()
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, _browser, _pw = self._start(adapter, context, tmp)
            source = types.SimpleNamespace(
                page=FakePage(url="https://outside.example/token=secret")
            )
            detail = {"value": "credential-secret"}

            from contextlib import redirect_stdout
            from io import StringIO

            output = StringIO()
            with redirect_stdout(output):
                context.binding_callback(source, detail)

            logged = output.getvalue()
            self.assertNotIn("outside.example", logged)
            self.assertNotIn("credential-secret", logged)
            self.assertEqual(inner.events, [])
            self.assertEqual(recorder.rejected_events, 1)

    def test_a_page_outside_the_authorized_origins_is_not_instrumented(self) -> None:
        adapter = load_adapter()
        context = FakeContext([FakePage()])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, _inner, _browser, _pw = self._start(adapter, context, tmp)
            stray = FakePage(url="http://evil.internal/steal")
            context.open_popup(stray)
            self.assertEqual(recorder.late_pages, 0)
            self.assertEqual(stray.frames[0].evaluated, [])

    def test_attachment_refuses_a_browser_outside_the_authorized_origins(self) -> None:
        adapter = load_adapter()
        context = FakeContext([FakePage(url="http://elsewhere.internal/")])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "authorized Teach origins"):
                self._start(adapter, context, tmp)

    def test_a_detached_frame_does_not_abort_attachment(self) -> None:
        adapter = load_adapter()
        page = FakePage(frames=[FakeFrame("main"), FakeFrame("gone", raises=True)])
        context = FakeContext([page])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, _inner, _browser, _pw = self._start(adapter, context, tmp)
            self.assertEqual(recorder.instrumented_frames, 1)

    def test_readiness_and_disconnect_leave_the_browser_running(self) -> None:
        adapter = load_adapter()
        context = FakeContext([FakePage()])
        with tempfile.TemporaryDirectory() as tmp:
            recorder, inner, browser, playwright = self._start(adapter, context, tmp)
            self.assertTrue(inner.primed)
            self.assertEqual(
                (Path(tmp) / "ready").read_text(encoding="utf-8"), "ready\n"
            )
            result = recorder.finish()
            self.assertTrue(inner.flushed)
            self.assertEqual(result, Path(tmp))
            self.assertEqual(browser.close_calls, 0)
            self.assertEqual(playwright.stop_calls, 1)


class CompileTests(unittest.TestCase):
    def _compile(self, adapter, schema_version, decisions_body=None):
        calls = []
        compile_module = types.ModuleType("openadapt_flow.compiler.compile")

        def compile_recording(source, bundle, **kwargs):
            calls.append((Path(source), Path(bundle), kwargs))
            Path(bundle).mkdir(parents=True)
            (Path(bundle) / "workflow.json").write_text(
                json.dumps({"schema_version": schema_version}), encoding="utf-8"
            )

        compile_module.compile_recording = compile_recording
        prior = sys.modules.get("openadapt_flow.compiler.compile")
        sys.modules["openadapt_flow.compiler.compile"] = compile_module
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source"
                source.mkdir()
                decisions = root / "decisions.json"
                decisions.write_text(
                    json.dumps(
                        decisions_body
                        or {
                            "workflow_name": "Export legacy report",
                            "param_overrides": {"step_001": "report_date"},
                            "secret_param_steps": [],
                        }
                    ),
                    encoding="utf-8",
                )
                return calls, adapter.compile_native_bundle(
                    source, decisions, root / "bundle"
                )
        finally:
            if prior is None:
                sys.modules.pop("openadapt_flow.compiler.compile", None)
            else:
                sys.modules["openadapt_flow.compiler.compile"] = prior

    def test_compile_delegates_to_upstream_and_emits_bounded_evidence(self) -> None:
        adapter = load_adapter()
        calls, evidence = self._compile(adapter, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2]["name"], "Export legacy report")
        self.assertFalse(calls[0][2]["annotate"])
        self.assertFalse(calls[0][2]["mine_effects"])
        self.assertEqual(evidence["actuation_class"], "ui_only")
        self.assertEqual(evidence["bundle_schema_version"], "2")
        self.assertFalse(evidence["execution_authority"])
        self.assertFalse(evidence["promotion_authority"])
        self.assertNotIn("workflow", evidence)
        self.assertNotIn("events", evidence)

    def test_an_unrecognised_bundle_schema_is_rejected_not_waved_through(self) -> None:
        adapter = load_adapter()
        # The UI-only walk keys on field names. A schema nobody has read is a
        # schema where the check may have silently stopped checking.
        with self.assertRaisesRegex(ValueError, "unrecognised"):
            self._compile(adapter, 99)

    def test_ui_only_bundle_check_rejects_api_binding(self) -> None:
        adapter = load_adapter()
        with self.assertRaisesRegex(ValueError, "crosses UI actuation"):
            adapter._assert_ui_only(
                {
                    "schema_version": 2,
                    "steps": [
                        {
                            "id": "step_001",
                            "api_binding": {"method": "POST", "path": "/api/export"},
                        }
                    ],
                }
            )


class ArchiveTests(unittest.TestCase):
    def _populate(self, source: Path) -> None:
        (source / "frames").mkdir(parents=True)
        (source / "meta.json").write_text('{"id":"x"}', encoding="utf-8")
        (source / "events.jsonl").write_text("{}\n", encoding="utf-8")
        (source / "frames" / "0000_before.png").write_bytes(b"png" * 1024)

    def test_archive_is_byte_stable_and_rejects_symlinks(self) -> None:
        adapter = load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._populate(source)
            first = root / "first.zip"
            second = root / "second.zip"
            evidence_one = adapter.archive_native_directory(source, first)
            evidence_two = adapter.archive_native_directory(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(evidence_one, evidence_two)
            self.assertEqual(evidence_one["archive_format"], "deterministic-zip-v1")
            self.assertEqual(evidence_one["size_bytes"], first.stat().st_size)

            try:
                (source / "linked").symlink_to(source / "meta.json")
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symlink"):
                adapter.archive_native_directory(source, root / "linked.zip")

    def test_archive_enforces_an_explicit_size_limit_while_writing(self) -> None:
        adapter = load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._populate(source)
            with self.assertRaisesRegex(ValueError, "archive size limit"):
                adapter.archive_native_directory(
                    source, root / "capped.zip", max_bytes=16
                )

    def test_archive_never_holds_a_whole_artifact_in_memory(self) -> None:
        adapter = load_adapter()
        source_text = ADAPTER_PATH.read_text(encoding="utf-8")
        # Screenshot-heavy recordings are far larger than a worker pod should
        # buffer. Reading the archive back whole was the previous OOM path.
        self.assertNotIn("output_path.read_bytes()", source_text)
        self.assertIn("_STREAM_CHUNK_BYTES", source_text)


if __name__ == "__main__":
    unittest.main()
