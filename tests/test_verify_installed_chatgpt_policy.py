#!/usr/bin/python3
"""Fixture tests for the installed ChatGPT Desktop policy verifier."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import stat
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "runtimes/chatgpt-desktop/verify-installed-policy.py"
LOADER = importlib.machinery.SourceFileLoader("grotto_installed_policy", str(VERIFIER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
policy = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(policy)

SAFE_BROWSER_BUNDLE = r'''
function codexLinuxTrustedBrowserClientSha256s(hashes) {
  return hashes;
}
function makeRuntime({nodePath:a,nodeReplPath:b,shouldUseWslPaths:c,
  trustedBrowserClientSha256s:d}) {
  d=codexLinuxTrustedBrowserClientSha256s(d);
  return {nodePath:a,nodeReplPath:b,shouldUseWslPaths:c,
    trustedBrowserClientSha256s:d};
}
const config = {[`mcp_servers.${name}`]:{args:[],command:cmd,env,
  startup_timeout_sec:120}};
'''


class InstalledPolicyVerifierTest(unittest.TestCase):
    def fixture(self, sources: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name) / "opt" / "chatgpt"
        root.mkdir(parents=True)
        for name, source in sources.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return temporary, root

    def test_trusted_hash_present_and_auto_approval_absent_passes(self) -> None:
        temporary, root = self.fixture({"resources/app/main.js": SAFE_BROWSER_BUNDLE})
        with temporary:
            inspection = policy.inspect_installed_application(root)

        self.assertTrue(inspection.node_repl_exposed)
        self.assertFalse(inspection.node_repl_auto_approved)
        self.assertTrue(inspection.browser_use_trusted_client_hash_patch)

    def test_normalized_auto_approval_variants_fail(self) -> None:
        variants = (
            'tools: { js: { approval_mode: "approve" } }',
            "tools:{js:{approval_mode:`approve`}}",
            "'tools' : { 'js' : { 'approval_mode' : 'approve' } }",
        )
        for index, unsafe in enumerate(variants):
            with self.subTest(index=index):
                temporary, root = self.fixture(
                    {"resources/app/main.js": SAFE_BROWSER_BUNDLE + unsafe}
                )
                with temporary, self.assertRaisesRegex(
                    policy.VerificationError, "automatic approval"
                ):
                    policy.inspect_installed_application(root)

    def test_browser_use_without_trusted_hash_patch_fails(self) -> None:
        source = r'''
function makeRuntime({nodePath:a,nodeReplPath:b,shouldUseWslPaths:c,
  trustedBrowserClientSha256s:d}) { return d; }
const config = {[`mcp_servers.${name}`]:{startup_timeout_sec:120}};
'''
        temporary, root = self.fixture({"resources/app/main.js": source})
        with temporary, self.assertRaisesRegex(
            policy.VerificationError, "without the trusted-client hash adjustment"
        ):
            policy.inspect_installed_application(root)

    def test_node_repl_absent_upstream_is_not_claimed_exposed(self) -> None:
        temporary, root = self.fixture(
            {"resources/app/main.js": "const ordinaryDesktopBundle = true;"}
        )
        with temporary:
            inspection = policy.inspect_installed_application(root)

        self.assertFalse(inspection.node_repl_exposed)
        self.assertFalse(inspection.node_repl_auto_approved)
        self.assertFalse(inspection.browser_use_trusted_client_hash_patch)

    def test_ambiguous_changed_bundle_fails_closed(self) -> None:
        temporary, root = self.fixture(
            {"resources/app/chunk.js": "const changed = 'node_repl';"}
        )
        with temporary, self.assertRaisesRegex(
            policy.VerificationError, "ambiguous"
        ):
            policy.inspect_installed_application(root)

    def test_empty_or_unreadable_bundle_structure_fails_closed(self) -> None:
        temporary, root = self.fixture({"README.txt": "not a bundle"})
        with temporary, self.assertRaisesRegex(
            policy.VerificationError, "no JavaScript bundles"
        ):
            policy.inspect_installed_application(root)

    def test_manifest_is_derived_and_immutable(self) -> None:
        temporary, root = self.fixture({"resources/app/main.js": SAFE_BROWSER_BUNDLE})
        with temporary:
            inspection = policy.inspect_installed_application(root)
            manifest = inspection.manifest("7d4049b")
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
