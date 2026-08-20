from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = (
    REPO_ROOT
    / "runtimes"
    / "openadapt-teach"
    / "grotto_openadapt_teach.py"
)


def load_adapter():
    spec = importlib.util.spec_from_file_location("grotto_openadapt_teach", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("adapter module is not loadable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.bindings: list[str] = []
        self.init_scripts: list[str] = []
        self.evaluated_scripts: list[str] = []
        self.goto_urls: list[str] = []
        self.handlers: dict[str, object] = {}

    def expose_binding(self, name, callback) -> None:
        del callback
        self.bindings.append(name)

    def add_init_script(self, script) -> None:
        self.init_scripts.append(script)

    def evaluate(self, script) -> None:
        self.evaluated_scripts.append(script)

    def goto(self, url) -> None:
        self.url = url
        self.goto_urls.append(url)

    def wait_for_load_state(self, state) -> None:
        del state

    def on(self, event, callback) -> None:
        self.handlers[event] = callback


class FakeContext:
    def __init__(self, pages) -> None:
        self.pages = pages


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


class FakePlaywrightStarter:
    def __init__(self, playwright) -> None:
        self.playwright = playwright

    def start(self):
        return self.playwright


class FakeBackend:
    def __init__(self, page) -> None:
        self.page = page


class FakeRecorder:
    instances = []

    def __init__(self, backend, out_dir, *, app_url, **settle) -> None:
        self.backend = backend
        self.out_dir = Path(out_dir)
        self.app_url = app_url
        self.settle = settle
        self.finished = False
        type(self).instances.append(self)

    def _wait_settled(self) -> bytes:
        return b"png"

    def finish(self) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "meta.json").write_text("{}", encoding="utf-8")
        self.finished = True
        return self.out_dir


class FakeInteractiveRecorder:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        self._pyq = []
        self._pending_type = None
        self._pending_scroll = None
        self._settle = {}
        self._system_of_record_reader = None
        self.done = False
        self.page = None
        self.backend = None
        self.recorder = None

    def _flush_type(self) -> None:
        return None

    def _flush_scroll(self) -> None:
        return None

    def _structural_state(self):
        return {}


class OpenAdaptTeachAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeRecorder.instances.clear()

    def test_configuration_rejects_non_loopback_cdp_and_non_ui_actuation(self) -> None:
        adapter = load_adapter()
        base = {
            "teach_session_id": "teach-1",
            "cdp_url": "http://127.0.0.1:9222",
            "start_url": "https://target.internal/task",
            "source_dir": "source",
            "engine_release": {"release_id": "openadapt-flow-1.31.0"},
            "browser_runtime_release": {"release_id": "browser-runtime-1"},
            "adapter_release": {"release_id": "grotto-openadapt-teach-1"},
            "actuation_class": "ui_only",
        }
        self.assertEqual(adapter.TeachAttachConfig.from_mapping(base).actuation_class, "ui_only")

        remote = {**base, "cdp_url": "http://browser-runtime:9222"}
        with self.assertRaisesRegex(ValueError, "loopback"):
            adapter.TeachAttachConfig.from_mapping(remote)

        api = {**base, "actuation_class": "api"}
        with self.assertRaisesRegex(ValueError, "ui_only"):
            adapter.TeachAttachConfig.from_mapping(api)

    def test_attachment_reuses_existing_page_and_instruments_current_and_future_documents(self) -> None:
        adapter = load_adapter()
        page = FakePage()
        browser = FakeBrowser([FakeContext([page])])
        playwright = FakePlaywright(browser)

        fake_interactive = types.ModuleType("openadapt_flow.interactive_recorder")
        fake_interactive._INIT_JS = "const secrets=__SECRET_NAMES__; const ids=__IDENT_NAMES__; const keys=__SPECIAL_KEYS__;"
        fake_interactive._SPECIAL_KEYS = ("Enter", "Tab")
        fake_interactive.InteractiveRecorder = FakeInteractiveRecorder
        fake_backend = types.ModuleType("openadapt_flow.backends.playwright_backend")
        fake_backend.PlaywrightBackend = FakeBackend
        fake_recorder = types.ModuleType("openadapt_flow.recorder")
        fake_recorder.Recorder = FakeRecorder
        fake_playwright = types.ModuleType("playwright.sync_api")
        fake_playwright.sync_playwright = lambda: FakePlaywrightStarter(playwright)

        modules = {
            "openadapt_flow.interactive_recorder": fake_interactive,
            "openadapt_flow.backends.playwright_backend": fake_backend,
            "openadapt_flow.recorder": fake_recorder,
            "playwright.sync_api": fake_playwright,
        }
        old = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config = adapter.TeachAttachConfig.from_mapping(
                    {
                        "teach_session_id": "teach-1",
                        "cdp_url": "http://127.0.0.1:9222",
                        "start_url": "https://target.internal/task",
                        "source_dir": tmp,
                        "ready_file": str(Path(tmp) / "ready"),
                        "engine_release": {"release_id": "flow"},
                        "browser_runtime_release": {"release_id": "browser"},
                        "adapter_release": {"release_id": "adapter"},
                        "actuation_class": "ui_only",
                        "secret_fields": ["password"],
                    }
                )
                recorder = adapter.AttachedInteractiveRecorder(config)
                recorder.start()
                result = recorder.finish()
                ready_content = config.ready_file.read_text(encoding="utf-8")

            self.assertEqual(playwright.chromium.endpoints, ["http://127.0.0.1:9222"])
            self.assertIs(recorder.page, page)
            self.assertEqual(page.bindings, ["__oaflow_emit"])
            self.assertEqual(len(page.init_scripts), 1)
            self.assertEqual(page.evaluated_scripts, page.init_scripts)
            self.assertEqual(page.goto_urls, ["https://target.internal/task"])
            self.assertEqual(browser.close_calls, 0)
            self.assertEqual(playwright.stop_calls, 1)
            self.assertTrue(result.name == Path(config.source_dir).name)
            self.assertEqual(ready_content, "ready\n")
        finally:
            for name, prior in old.items():
                if prior is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prior

    def test_compile_delegates_to_upstream_and_emits_bounded_evidence(self) -> None:
        adapter = load_adapter()
        calls = []
        compile_module = types.ModuleType("openadapt_flow.compiler.compile")

        def compile_recording(source, bundle, **kwargs):
            calls.append((Path(source), Path(bundle), kwargs))
            Path(bundle).mkdir(parents=True)
            (Path(bundle) / "workflow.json").write_text(
                json.dumps({"schema_version": 2}), encoding="utf-8"
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
                        {
                            "workflow_name": "Export legacy report",
                            "param_overrides": {"step_001": "report_date"},
                            "secret_param_steps": [],
                        }
                    ),
                    encoding="utf-8",
                )
                bundle = root / "bundle"
                evidence = adapter.compile_native_bundle(source, decisions, bundle)

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2]["name"], "Export legacy report")
            self.assertFalse(calls[0][2]["annotate"])
            self.assertFalse(calls[0][2]["mine_effects"])
            self.assertEqual(evidence["actuation_class"], "ui_only")
            self.assertEqual(evidence["bundle_schema_version"], "2")
            self.assertNotIn("workflow", evidence)
            self.assertNotIn("events", evidence)
        finally:
            if prior is None:
                sys.modules.pop("openadapt_flow.compiler.compile", None)
            else:
                sys.modules["openadapt_flow.compiler.compile"] = prior

    def test_native_directory_archive_is_stable_and_rejects_symlinks(self) -> None:
        adapter = load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "frames").mkdir(parents=True)
            (source / "meta.json").write_text('{"id":"x"}', encoding="utf-8")
            (source / "events.jsonl").write_text("{}\n", encoding="utf-8")
            (source / "frames" / "0000_before.png").write_bytes(b"png")
            first = root / "first.zip"
            second = root / "second.zip"
            evidence_one = adapter.archive_native_directory(source, first)
            evidence_two = adapter.archive_native_directory(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(evidence_one, evidence_two)
            self.assertEqual(evidence_one["archive_format"], "deterministic-zip-v1")

            try:
                (source / "linked").symlink_to(source / "meta.json")
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symlink"):
                adapter.archive_native_directory(source, root / "linked.zip")

    def test_ui_only_bundle_check_rejects_api_binding(self) -> None:
        adapter = load_adapter()
        with self.assertRaisesRegex(ValueError, "crosses UI actuation"):
            adapter._assert_ui_only(
                {
                    "schema_version": 2,
                    "steps": [
                        {
                            "id": "step_001",
                            "api_binding": {
                                "method": "POST",
                                "path": "/api/export",
                            },
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
