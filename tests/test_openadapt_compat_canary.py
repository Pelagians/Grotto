"""The version canary must fail loudly, not degrade quietly.

The hazard this guards against is specific: if upstream renames a private
symbol, the adapter does not crash. It records an empty event stream and the
Teach session looks like it succeeded. These tests drive the canary against
synthesised Flow modules so the failure mode is proven, not asserted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPAT_PATH = REPO_ROOT / "runtimes" / "openadapt-teach" / "openadapt_compat.py"

FLOW_MODULES = (
    "openadapt_flow",
    "openadapt_flow.interactive_recorder",
    "openadapt_flow.recorder",
    "openadapt_flow.backends",
    "openadapt_flow.backends.playwright_backend",
)


def load_compat():
    spec = importlib.util.spec_from_file_location("openadapt_compat", COMPAT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeInteractiveRecorder:
    """A stand-in with the private surface Flow 1.31 actually exposes."""

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        self._pyq = []
        self._settle = {}
        self._system_of_record_reader = None
        self.done = False
        self.page = None
        self.backend = None
        self.recorder = None

    def pump(self) -> bool:
        return False

    def _flush_type(self) -> None:
        return None

    def _flush_scroll(self) -> None:
        return None

    def _structural_state(self):
        return {}


class EagerInteractiveRecorder(FakeInteractiveRecorder):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.page = object()


def install_flow(
    *,
    init_js: str | None = None,
    recorder_class=FakeInteractiveRecorder,
    special_keys=("Enter", "Tab"),
    drop: tuple[str, ...] = (),
    upstream_attach: bool = False,
):
    if init_js is None:
        init_js = (
            "const s=__SECRET_NAMES__; const i=__IDENT_NAMES__; "
            "const k=__SPECIAL_KEYS__; window.__oaflow_emit(x);"
        )
    package = types.ModuleType("openadapt_flow")
    package.__path__ = []  # type: ignore[attr-defined]
    interactive = types.ModuleType("openadapt_flow.interactive_recorder")
    if "_INIT_JS" not in drop:
        interactive._INIT_JS = init_js
    if "_SPECIAL_KEYS" not in drop:
        interactive._SPECIAL_KEYS = special_keys

    if upstream_attach:

        class UpstreamRecorder(recorder_class):
            def __init__(self, start_url, out_dir, *, context=None, owns_browser=True, **kw):
                super().__init__()

        interactive.InteractiveRecorder = UpstreamRecorder
    else:
        interactive.InteractiveRecorder = recorder_class

    inner = types.ModuleType("openadapt_flow.recorder")

    class FlowRecorder:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def _wait_settled(self):
            return b"png"

        def finish(self):
            return Path(".")

    if "_wait_settled" in drop:
        del FlowRecorder._wait_settled
    inner.Recorder = FlowRecorder

    backends = types.ModuleType("openadapt_flow.backends")
    backends.__path__ = []  # type: ignore[attr-defined]
    playwright_backend = types.ModuleType("openadapt_flow.backends.playwright_backend")
    playwright_backend.PlaywrightBackend = lambda page: types.SimpleNamespace(page=page)

    return {
        "openadapt_flow": package,
        "openadapt_flow.interactive_recorder": interactive,
        "openadapt_flow.recorder": inner,
        "openadapt_flow.backends": backends,
        "openadapt_flow.backends.playwright_backend": playwright_backend,
    }


class CanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compat = load_compat()
        self._saved = {name: sys.modules.get(name) for name in FLOW_MODULES}
        self.compat._installed_version = lambda: self.compat.PINNED_FLOW_VERSION

    def tearDown(self) -> None:
        for name, prior in self._saved.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def _install(self, **kwargs) -> None:
        sys.modules.update(install_flow(**kwargs))

    def test_reports_healthy_private_composition_for_the_pinned_release(self) -> None:
        self._install()
        report = self.compat.probe()
        self.assertTrue(report.ok, report.as_json())
        self.assertEqual(report.strategy, "private_composition")
        self.assertFalse(report.supports_upstream_attach)
        self.assertEqual(report.missing, {})

    def test_a_renamed_private_constant_fails_the_canary(self) -> None:
        self._install(drop=("_INIT_JS",))
        report = self.compat.probe()
        self.assertFalse(report.ok)
        self.assertIn("_INIT_JS", report.missing["openadapt_flow.interactive_recorder"])
        with self.assertRaises(self.compat.CompatibilityError):
            self.compat.require_compatible()

    def test_a_renamed_event_binding_fails_the_canary(self) -> None:
        # The injected script and the Python side agree on a private name. If
        # that name moves, every event silently stops arriving.
        self._install(
            init_js="const s=__SECRET_NAMES__; const i=__IDENT_NAMES__; "
            "const k=__SPECIAL_KEYS__; window.__oaflow_send(x);"
        )
        report = self.compat.probe()
        self.assertFalse(report.ok)
        self.assertIn(
            self.compat.EVENT_BINDING_NAME, report.missing["_INIT_JS placeholders"]
        )

    def test_a_removed_placeholder_fails_the_canary(self) -> None:
        self._install(init_js="const k=__SPECIAL_KEYS__; window.__oaflow_emit(x);")
        report = self.compat.probe()
        self.assertFalse(report.ok)
        self.assertIn("__SECRET_NAMES__", report.missing["_INIT_JS placeholders"])

    def test_a_removed_recorder_method_fails_the_canary(self) -> None:
        self._install(drop=("_wait_settled",))
        report = self.compat.probe()
        self.assertFalse(report.ok)
        self.assertIn("_wait_settled", report.missing["Recorder instance"])

    def test_an_unpinned_flow_version_is_reported_as_unverified(self) -> None:
        self._install()
        self.compat._installed_version = lambda: "1.32.0"
        report = self.compat.probe()
        self.assertTrue(any("not the pinned" in note for note in report.notes))

    def test_a_missing_distribution_is_not_silently_ok(self) -> None:
        self.compat._installed_version = lambda: None
        report = self.compat.probe()
        self.assertFalse(report.ok)
        self.assertEqual(report.strategy, "unavailable")

    def test_upstream_attach_support_is_detected_and_preferred(self) -> None:
        self._install(upstream_attach=True)
        report = self.compat.probe()
        self.assertTrue(report.ok)
        self.assertEqual(report.strategy, "upstream")
        self.assertTrue(report.supports_upstream_attach)
        self.assertTrue(
            any("retire the private seam" in note for note in report.notes),
            report.notes,
        )


class InstanceSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compat = load_compat()
        self._saved = {name: sys.modules.get(name) for name in FLOW_MODULES}

    def tearDown(self) -> None:
        for name, prior in self._saved.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def test_a_lazy_constructor_passes_instance_verification(self) -> None:
        sys.modules.update(install_flow())
        inner = self.compat.build_inner_recorder(
            start_url="http://target:8000/",
            source_dir=Path("."),
            secret_fields=(),
            param_fields=(),
            identifier_fields=(),
            stop_when=None,
        )
        self.assertIsNone(inner.page)

    def test_an_eager_constructor_is_refused_rather_than_tolerated(self) -> None:
        # The worker image contains no browser binary on purpose. An eager
        # upstream __init__ would try to launch one.
        sys.modules.update(install_flow(recorder_class=EagerInteractiveRecorder))
        with self.assertRaisesRegex(self.compat.CompatibilityError, "no longer lazy"):
            self.compat.build_inner_recorder(
                start_url="http://target:8000/",
                source_dir=Path("."),
                secret_fields=(),
                param_fields=(),
                identifier_fields=(),
                stop_when=None,
            )

    def test_missing_private_instance_state_is_refused(self) -> None:
        class Stripped(FakeInteractiveRecorder):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                del self._pyq

        sys.modules.update(install_flow(recorder_class=Stripped))
        with self.assertRaisesRegex(self.compat.CompatibilityError, "_pyq"):
            self.compat.build_inner_recorder(
                start_url="http://target:8000/",
                source_dir=Path("."),
                secret_fields=(),
                param_fields=(),
                identifier_fields=(),
                stop_when=None,
            )

    def test_init_script_substitution_uses_upstream_template_only(self) -> None:
        sys.modules.update(install_flow())
        rendered = self.compat.render_init_script(
            secret_fields=("password",), identifier_fields=("account",)
        )
        self.assertIn('["password"]', rendered)
        self.assertIn('["account"]', rendered)
        self.assertIn('["Enter", "Tab"]', rendered)
        for token in self.compat.INIT_JS_PLACEHOLDERS:
            self.assertNotIn(token, rendered)


if __name__ == "__main__":
    unittest.main()
