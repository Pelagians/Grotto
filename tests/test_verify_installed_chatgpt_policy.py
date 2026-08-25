#!/usr/bin/python3
"""Fixture tests for the installed ChatGPT package policy verifier."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "runtimes/chatgpt-desktop/verify-installed-policy.py"
LOADER = importlib.machinery.SourceFileLoader("grotto_installed_policy", str(VERIFIER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
policy = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = policy
LOADER.exec_module(policy)

PACKAGE_VERSION = "26.820.60940"
PACKAGE = {
    "name": "chatgpt",
    "version": PACKAGE_VERSION,
    "architecture": "amd64",
}
# Minified shapes taken from the vendor bundle: node_repl is wired up, and the
# approval mode is a setting rather than a hardcoded approval.
VENDOR_ASAR = (
    "const hostConfig={browserClientPath:pathSchema,nodeReplPath:pathSchema};\n"
    "const defaults={tools:null,default_tools_approval_mode:null};\n"
)


class InstalledPolicyVerifierTest(unittest.TestCase):
    def fixture(self, sources: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name) / "usr" / "lib" / "chatgpt"
        root.mkdir(parents=True)
        for name, source in sources.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return temporary, root

    def vendor_sources(self, archive: str = VENDOR_ASAR) -> dict[str, str]:
        return {
            "resources/app.asar": archive,
            "resources/plugins/openai-bundled/plugins/browser/server.mjs": (
                "export const client='browser-client.mjs';\n"
            ),
        }

    def installed(self, **overrides: str):
        record = {**PACKAGE, **overrides}
        completed = mock.Mock(
            returncode=0,
            stdout="\n".join(
                (
                    record["name"],
                    record["version"],
                    record["architecture"],
                    "install ok installed",
                )
            ),
            stderr="",
        )
        return mock.patch.object(policy.subprocess, "run", return_value=completed)

    def test_vendor_bundle_without_auto_approval_passes(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        with temporary, self.installed():
            manifest = policy.build_manifest(root, PACKAGE_VERSION)

        self.assertEqual(manifest["schema_version"], policy.SCHEMA_VERSION)
        self.assertEqual(manifest["package"], PACKAGE)
        self.assertTrue(manifest["node_repl"]["exposed"])
        self.assertFalse(manifest["node_repl"]["auto_approved"])
        self.assertTrue(manifest["node_repl"]["verified"])
        self.assertEqual(
            manifest["node_repl"]["verification_source"],
            "installed-vendor-package",
        )
        self.assertTrue(manifest["browser_use"]["present"])
        self.assertFalse(manifest["browser_use"]["trusted_client_hash_patch"])
        self.assertTrue(manifest["browser_use"]["verified"])

    def test_normalized_auto_approval_variants_fail(self) -> None:
        variants = (
            'tools: { js: { approval_mode: "approve" } }',
            "tools:{js:{approval_mode:`approve`}}",
            "'tools' : { 'js' : { 'approval_mode' : 'approve' } }",
        )
        for index, unsafe in enumerate(variants):
            with self.subTest(index=index):
                temporary, root = self.fixture(
                    self.vendor_sources(VENDOR_ASAR + unsafe)
                )
                with temporary, self.installed(), self.assertRaisesRegex(
                    policy.VerificationError, "automatic approval"
                ):
                    policy.build_manifest(root, PACKAGE_VERSION)

    def test_auto_approval_in_a_loose_script_fails(self) -> None:
        sources = self.vendor_sources()
        sources["resources/plugins/openai-bundled/plugins/browser/server.mjs"] = (
            "const c={tools:{js:{approval_mode:'approve'}}};\n"
        )
        temporary, root = self.fixture(sources)
        with temporary, self.installed(), self.assertRaisesRegex(
            policy.VerificationError, "automatic approval"
        ):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_auto_approval_across_a_read_boundary_is_still_found(self) -> None:
        unsafe = "tools:{js:{approval_mode:'approve'}}"
        # Straddle the window boundary so the overlap, not luck, catches it.
        padding = "/*pad*/" * ((policy.SCAN_WINDOW_BYTES // 7) - 1)
        temporary, root = self.fixture(
            self.vendor_sources(VENDOR_ASAR + padding + unsafe + padding)
        )
        with temporary, self.installed(), self.assertRaisesRegex(
            policy.VerificationError, "automatic approval"
        ):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_node_repl_absent_upstream_is_not_claimed_exposed(self) -> None:
        temporary, root = self.fixture(
            {"resources/app.asar": "const ordinaryDesktopBundle = true;"}
        )
        with temporary, self.installed():
            manifest = policy.build_manifest(root, PACKAGE_VERSION)

        self.assertFalse(manifest["node_repl"]["exposed"])
        self.assertFalse(manifest["node_repl"]["auto_approved"])
        self.assertFalse(manifest["browser_use"]["present"])

    def test_missing_archive_fails_closed(self) -> None:
        temporary, root = self.fixture({"resources/README.txt": "not a bundle"})
        with temporary, self.installed(), self.assertRaisesRegex(
            policy.VerificationError, "no app.asar archive"
        ):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_missing_root_fails_closed(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        with temporary, self.installed(), self.assertRaisesRegex(
            policy.VerificationError, "installed application root is missing"
        ):
            policy.build_manifest(root / "absent", PACKAGE_VERSION)

    def test_version_drift_from_the_pinned_build_fails(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        with temporary, self.installed(version="26.821.1"), self.assertRaisesRegex(
            policy.VerificationError, "does not match the pinned build version"
        ):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_half_installed_package_fails(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        completed = mock.Mock(
            returncode=0,
            stdout="chatgpt\n{}\namd64\ninstall ok half-configured".format(
                PACKAGE_VERSION
            ),
            stderr="",
        )
        with temporary, mock.patch.object(
            policy.subprocess, "run", return_value=completed
        ), self.assertRaisesRegex(policy.VerificationError, "not fully installed"):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_absent_package_fails(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        completed = mock.Mock(returncode=1, stdout="", stderr="no packages found")
        with temporary, mock.patch.object(
            policy.subprocess, "run", return_value=completed
        ), self.assertRaisesRegex(policy.VerificationError, "is not installed"):
            policy.build_manifest(root, PACKAGE_VERSION)

    def test_manifest_is_derived_and_immutable(self) -> None:
        temporary, root = self.fixture(self.vendor_sources())
        with temporary, self.installed():
            manifest = policy.build_manifest(root, PACKAGE_VERSION)
            destination = root.parent / "security.json"
            policy.write_manifest(destination, manifest)
            loaded = json.loads(destination.read_text(encoding="utf-8"))
            mode = stat.S_IMODE(destination.stat().st_mode)

        self.assertEqual(loaded, manifest)
        self.assertEqual(mode, 0o444)
        self.assertTrue(loaded["node_repl"]["verified"])
        self.assertFalse(loaded["node_repl"]["auto_approved"])
        self.assertTrue(loaded["browser_use"]["verified"])


if __name__ == "__main__":
    unittest.main()
