#!/usr/bin/env python3
"""The only place Grotto is allowed to touch OpenAdapt Flow internals.

Flow 1.31 does not publish a caller-owned attach lifecycle, so the research
spike has to compose around private ``InteractiveRecorder`` state. That coupling
is contained here so it has exactly one blast radius, one inventory, and one
canary. No other Grotto module may import ``openadapt_flow`` private names.

Two strategies are supported, in preference order:

``upstream``
    Flow exposes ``InteractiveRecorder(context=..., owns_browser=False)``.
    Grotto hands over the caller-owned context and touches nothing private.
    This does not exist yet; the probe detects it the moment it ships.

``private_composition``
    The research fallback. Every private symbol is declared in
    ``PRIVATE_SYMBOLS`` and resolved through ``probe()``, so an upstream rename
    fails loudly at startup instead of silently producing an empty event
    stream, which was the real hazard of the original inline coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

# The exact Flow release this compatibility seam was written against. The
# canary compares against the installed distribution and refuses to guess.
PINNED_FLOW_VERSION = "1.31.0"
PINNED_FLOW_SOURCE_COMMIT = "faf9945537d4011baeb36ce5f063b6e1814903e6"

# The binding name Flow's injected recorder script calls. This is a private
# wire contract between _INIT_JS and the Python side; it is declared here so a
# rename is a canary failure rather than a silent loss of every event.
EVENT_BINDING_NAME = "__oaflow_emit"

# module path -> attribute names Grotto depends on that upstream does not
# publish. Ordered for a stable canary report.
PRIVATE_SYMBOLS: dict[str, tuple[str, ...]] = {
    "openadapt_flow.interactive_recorder": ("_INIT_JS", "_SPECIAL_KEYS"),
}

# Private *methods* on InteractiveRecorder. These live on the class, so the
# canary can find them without constructing anything.
PRIVATE_RECORDER_METHODS: tuple[str, ...] = (
    "_flush_type",
    "_flush_scroll",
    "_structural_state",
)

# Private *instance* attributes Grotto reads. These are assigned in Flow's
# __init__ and are not class attributes, so they cannot be probed statically;
# they are verified on the real object in ``build_inner_recorder``.
PRIVATE_RECORDER_INSTANCE_READS: tuple[str, ...] = (
    "_pyq",
    "_settle",
    "_system_of_record_reader",
)

# Private instance attributes Grotto writes to reach the same post-start state
# Flow's own ``start`` would have produced. Declared for the inventory; their
# absence before assignment is not an error.
PRIVATE_RECORDER_INSTANCE_WRITES: tuple[str, ...] = (
    "_last_frame",
    "_last_structural",
)

# Private methods read on a Recorder instance. Also class-level.
PRIVATE_INNER_RECORDER_ATTRS: tuple[str, ...] = ("_wait_settled",)

# Placeholder tokens Grotto substitutes into Flow's injected script. Upstream
# owns the template; Grotto owns none of the recording semantics, only the
# substitution, and only because upstream does not do it for an injected page.
INIT_JS_PLACEHOLDERS: tuple[str, ...] = (
    "__SECRET_NAMES__",
    "__IDENT_NAMES__",
    "__SPECIAL_KEYS__",
)


class CompatibilityError(RuntimeError):
    """The installed Flow release does not match this compatibility seam."""


@dataclass(frozen=True)
class CompatReport:
    """What the canary found. Serialized verbatim into CI output."""

    installed_version: str | None
    pinned_version: str = PINNED_FLOW_VERSION
    strategy: str = "unavailable"
    supports_upstream_attach: bool = False
    present: dict[str, list[str]] = field(default_factory=dict)
    missing: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and self.strategy != "unavailable"

    def as_json(self) -> dict[str, Any]:
        return {
            "installed_version": self.installed_version,
            "pinned_version": self.pinned_version,
            "version_matches": self.installed_version == self.pinned_version,
            "strategy": self.strategy,
            "supports_upstream_attach": self.supports_upstream_attach,
            "present": self.present,
            "missing": self.missing,
            "notes": self.notes,
            "ok": self.ok,
        }


def _installed_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    for name in ("openadapt-flow", "openadapt_flow"):
        try:
            return version(name)
        except PackageNotFoundError:
            continue
    return None


def _supports_upstream_attach() -> bool:
    """True once Flow accepts a caller-owned context and disowns the browser."""
    try:
        import inspect

        from openadapt_flow.interactive_recorder import InteractiveRecorder
    except Exception:
        return False
    try:
        parameters = inspect.signature(InteractiveRecorder).parameters
    except (TypeError, ValueError):
        return False
    return "context" in parameters and "owns_browser" in parameters


def probe() -> CompatReport:
    """Inventory the installed Flow release without importing Playwright."""
    import importlib

    installed = _installed_version()
    notes: list[str] = []
    if installed is None:
        return CompatReport(
            installed_version=None,
            notes=["openadapt-flow is not installed in this interpreter"],
        )
    if installed != PINNED_FLOW_VERSION:
        notes.append(
            f"installed openadapt-flow {installed} is not the pinned "
            f"{PINNED_FLOW_VERSION}; the private seam is unverified"
        )

    if _supports_upstream_attach():
        return CompatReport(
            installed_version=installed,
            strategy="upstream",
            supports_upstream_attach=True,
            notes=[
                *notes,
                "upstream caller-owned attach is available; retire the private seam",
            ],
        )

    present: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}
    for module_path, names in PRIVATE_SYMBOLS.items():
        try:
            module = importlib.import_module(module_path)
        except Exception as error:
            missing[module_path] = [f"module import failed: {error}"]
            continue
        for name in names:
            bucket = present if hasattr(module, name) else missing
            bucket.setdefault(module_path, []).append(name)

    try:
        recorder_module = importlib.import_module("openadapt_flow.interactive_recorder")
        recorder_class = recorder_module.InteractiveRecorder
    except Exception as error:
        missing["openadapt_flow.interactive_recorder.InteractiveRecorder"] = [
            f"unavailable: {error}"
        ]
        recorder_class = None
        recorder_module = None

    if recorder_class is not None:
        key = "InteractiveRecorder"
        for name in (*PRIVATE_RECORDER_METHODS, "pump"):
            bucket = present if hasattr(recorder_class, name) else missing
            bucket.setdefault(key, []).append(name)
        # Instance attributes assigned in Flow's __init__ are not visible on
        # the class, so they are checked on a real object at attach time by
        # ``verify_instance`` rather than guessed at here.
        notes.append(
            "instance attributes verified at attach time: "
            + ", ".join(PRIVATE_RECORDER_INSTANCE_READS)
        )

    if recorder_module is not None:
        template = getattr(recorder_module, "_INIT_JS", "")
        for token in INIT_JS_PLACEHOLDERS:
            if token not in template:
                missing.setdefault("_INIT_JS placeholders", []).append(token)
        if EVENT_BINDING_NAME not in template:
            missing.setdefault("_INIT_JS placeholders", []).append(EVENT_BINDING_NAME)

    try:
        inner = importlib.import_module("openadapt_flow.recorder").Recorder
        for name in PRIVATE_INNER_RECORDER_ATTRS:
            bucket = present if hasattr(inner, name) else missing
            bucket.setdefault("Recorder instance", []).append(name)
    except Exception as error:
        missing["openadapt_flow.recorder.Recorder"] = [f"unavailable: {error}"]

    return CompatReport(
        installed_version=installed,
        strategy="private_composition",
        supports_upstream_attach=False,
        present=present,
        missing=missing,
        notes=notes,
    )


def require_compatible() -> CompatReport:
    """Fail fast at startup rather than record an empty event stream."""
    report = probe()
    if not report.ok:
        raise CompatibilityError(
            "OpenAdapt Flow compatibility canary failed: "
            + json.dumps(report.as_json(), sort_keys=True)
        )
    return report


def render_init_script(
    *, secret_fields: tuple[str, ...], identifier_fields: tuple[str, ...]
) -> str:
    """Substitute Flow's own template. Grotto adds no recording semantics."""
    from openadapt_flow.interactive_recorder import _INIT_JS, _SPECIAL_KEYS

    return (
        _INIT_JS.replace("__SECRET_NAMES__", json.dumps(sorted(secret_fields)))
        .replace("__IDENT_NAMES__", json.dumps(sorted(identifier_fields)))
        .replace("__SPECIAL_KEYS__", json.dumps(list(_SPECIAL_KEYS)))
    )


def build_inner_recorder(
    *,
    start_url: str,
    source_dir,
    secret_fields: tuple[str, ...],
    param_fields: tuple[str, ...],
    identifier_fields: tuple[str, ...],
    stop_when: Callable[[], bool] | None,
):
    """Construct Flow's recorder without letting it own a browser.

    Flow's ``__init__`` is lazy today: it records intent and launches nothing.
    Grotto depends on that, so the dependency is asserted rather than assumed.
    A future eager ``__init__`` would otherwise launch a second browser inside
    an image that deliberately contains no browser binary.
    """
    from openadapt_flow.interactive_recorder import InteractiveRecorder

    inner = InteractiveRecorder(
        start_url,
        source_dir,
        secret_fields=secret_fields,
        param_fields=param_fields,
        identifier_fields=identifier_fields,
        headless=False,
        stop_when=stop_when,
    )
    for owned in ("page", "backend", "recorder"):
        if getattr(inner, owned, None) is not None:
            raise CompatibilityError(
                "Flow's InteractiveRecorder.__init__ is no longer lazy; it "
                f"already owns {owned!r}. Stop and use an upstream attach API."
            )
    verify_instance(inner)
    return inner


def verify_instance(inner) -> None:
    """Check the private instance surface the class-level canary cannot see."""
    absent = [name for name in PRIVATE_RECORDER_INSTANCE_READS if not hasattr(inner, name)]
    if absent:
        raise CompatibilityError(
            "OpenAdapt Flow no longer exposes the private recorder state this "
            f"adapter composes around: {absent}"
        )


def attach_inner_recorder(inner, *, page, source_dir, start_url):
    """Wire Flow's own backend and recorder onto a caller-owned page."""
    from openadapt_flow.backends.playwright_backend import PlaywrightBackend
    from openadapt_flow.recorder import Recorder

    inner.page = page
    inner.backend = PlaywrightBackend(page)
    inner.recorder = Recorder(
        inner.backend,
        source_dir,
        app_url=start_url,
        system_of_record_reader=inner._system_of_record_reader,
        **inner._settle,
    )
    return inner.recorder


def prime_settled_state(inner) -> None:
    """Reach the same post-start state Flow's own ``start`` would produce."""
    inner._last_frame = inner.recorder._wait_settled()
    inner._last_structural = inner._structural_state()


def emit_event(inner, detail) -> None:
    inner._pyq.append(detail)


def flush_pending(inner) -> None:
    inner._flush_type()
    inner._flush_scroll()
