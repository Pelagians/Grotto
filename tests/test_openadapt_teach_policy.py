"""Static policy for the Teach worker.

Two properties cannot be proven by unit-testing behaviour, because they are
claims about what the adapter never does and about where a coupling is allowed
to live. Both are checked against the source text so that a future edit which
quietly reintroduces them fails here rather than in production.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtimes" / "openadapt-teach"
ADAPTER_PATH = RUNTIME_DIR / "grotto_openadapt_teach.py"
COMPAT_PATH = RUNTIME_DIR / "openadapt_compat.py"
CONTAINERFILE = REPO_ROOT / "Containerfile.openadapt-teach"
LOCKFILE = RUNTIME_DIR / "requirements.lock.txt"

# Playwright calls that drive the browser rather than observe it. Loopback CDP
# contains exposure; it confers no authorization, so an attached worker holds
# full browser-session authority and the restraint has to be enforced in code.
DRIVING_CALLS = frozenset(
    {
        "goto",
        "click",
        "dblclick",
        "fill",
        "type",
        "press",
        "check",
        "uncheck",
        "select_option",
        "set_input_files",
        "reload",
        "go_back",
        "go_forward",
        "set_content",
        "tap",
        "drag_and_drop",
        "focus",
        "hover",
        "close",
        "kill",
        "route",
        "add_cookies",
        "clear_cookies",
        "grant_permissions",
    }
)

# The instrumentation calls the adapter is allowed to make on a page, frame or
# context. Anything else is either driving or unnecessary authority.
ALLOWED_PAGE_CALLS = frozenset(
    {"evaluate", "add_init_script", "expose_binding", "on"}
)


def _called_attribute_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


class PassiveRecordingPolicyTests(unittest.TestCase):
    def test_the_adapter_never_drives_the_browser(self) -> None:
        tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
        called = _called_attribute_names(tree)
        forbidden = sorted(called & DRIVING_CALLS)
        self.assertEqual(
            forbidden,
            [],
            f"the Teach recorder must stay passive; it calls {forbidden}",
        )

    def test_the_adapter_never_closes_the_caller_owned_browser(self) -> None:
        # ``close`` is covered by DRIVING_CALLS above; this pins the intent so
        # a future edit has to argue with the comment as well as the AST.
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("web-apps owns the browser lifecycle", source)
        tree = ast.parse(source)
        self.assertNotIn("close", _called_attribute_names(tree))

    def test_page_interaction_is_limited_to_instrumentation(self) -> None:
        tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
        interesting = _called_attribute_names(tree) & (
            DRIVING_CALLS | ALLOWED_PAGE_CALLS
        )
        self.assertTrue(interesting <= ALLOWED_PAGE_CALLS, sorted(interesting))


class CompatibilityContainmentTests(unittest.TestCase):
    def test_only_the_compat_module_imports_openadapt_private_names(self) -> None:
        adapter = ADAPTER_PATH.read_text(encoding="utf-8")
        # The adapter may import upstream's public compiler entrypoint; it may
        # not reach any private symbol or the recorder internals directly.
        for forbidden in (
            "interactive_recorder",
            "playwright_backend",
            "openadapt_flow.recorder",
            "_INIT_JS",
            "_SPECIAL_KEYS",
        ):
            self.assertNotIn(
                forbidden,
                adapter,
                f"{forbidden} must be reached through openadapt_compat only",
            )

    def test_every_private_dependency_is_declared_for_the_canary(self) -> None:
        compat = COMPAT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(compat)
        declared = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                declared.add(node.value)
        # Anything the seam touches privately must also be inventoried, or the
        # canary cannot detect an upstream rename.
        used = {
            attribute.attr
            for attribute in ast.walk(tree)
            if isinstance(attribute, ast.Attribute)
            and attribute.attr.startswith("_")
            and not attribute.attr.startswith("__")
        }
        undeclared = sorted(used - declared)
        self.assertEqual(
            undeclared,
            [],
            f"private OpenAdapt attributes not in the canary inventory: {undeclared}",
        )

    def test_the_documented_upstream_commit_is_the_corrected_one(self) -> None:
        expected = "faf9945537d4011baeb36ce5f063b6e1814903e6"
        self.assertIn(expected, COMPAT_PATH.read_text(encoding="utf-8"))
        docs = (REPO_ROOT / "docs" / "openadapt-teach.md").read_text(encoding="utf-8")
        self.assertIn(expected, docs)
        # The superseded value must not survive anywhere; Nereus freezes an
        # exact engine identity and two candidate commits is not an identity.
        self.assertNotIn("faf994b08ebc68d92413011edcc67b33168dfe70", docs)


class SupplyChainPinningTests(unittest.TestCase):
    def test_base_image_is_pinned_by_digest(self) -> None:
        containerfile = CONTAINERFILE.read_text(encoding="utf-8")
        self.assertRegex(containerfile, r"FROM [^\s]+@sha256:[0-9a-f]{64}")

    def test_python_dependencies_are_hash_pinned_and_unresolved(self) -> None:
        containerfile = CONTAINERFILE.read_text(encoding="utf-8")
        self.assertIn("--require-hashes", containerfile)
        self.assertIn("--no-deps", containerfile)
        lock = LOCKFILE.read_text(encoding="utf-8")
        pins = [
            line
            for line in lock.splitlines()
            if line and not line.startswith("#") and not line.strip().startswith("--")
        ]
        self.assertGreater(len(pins), 20)
        for line in pins:
            self.assertRegex(line.strip(), r"^[A-Za-z0-9._-]+==[^\s]+ \\\\?$")
        self.assertEqual(
            lock.count("--hash=sha256:"),
            len(pins),
            "every pinned distribution needs exactly one hash",
        )
        for direct in ("openadapt-flow==1.31.0", "playwright==1.60.0"):
            self.assertIn(direct, lock)

    def test_the_image_runs_the_compatibility_canary_at_build_time(self) -> None:
        containerfile = CONTAINERFILE.read_text(encoding="utf-8")
        self.assertIn("grotto-openadapt-teach canary", containerfile)


if __name__ == "__main__":
    unittest.main()
