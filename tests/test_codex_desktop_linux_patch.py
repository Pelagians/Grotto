#!/usr/bin/python3
"""Validate Grotto's containment patch against the pinned desktop wrapper."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTAINERFILE = ROOT / "Containerfile.chatgpt-desktop"
MAKEFILE = ROOT / "Makefile"
PATCH = ROOT / "patches/codex-desktop-linux/disable-auto-approved-node-repl.patch"
UPSTREAM_URL = "https://github.com/ilysenko/codex-desktop-linux.git"
REGISTRY = pathlib.Path(
    "scripts/patches/core/all-linux/main-process/browser-integrations/patch.js"
)
IMPLEMENTATION = pathlib.Path("scripts/patches/impl/main-process/browser.js")
DESCRIPTOR_ID = "browser-use-node-repl-approval"
ASSET_CALLER = "applyBrowserUseNodeReplApprovalAssets"
UNRELATED_IDS = {
    "linux-chrome-plugin-auto-install",
    "linux-bundled-plugin-reconcile-stale-snapshot",
    "linux-bundled-plugin-copy-permissions",
    "linux-browser-use-socket-directory",
    "linux-browser-use-route-liveness",
    "linux-chrome-extension-status",
}


def run(command: list[str], *, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed: {command!r}\n{completed.stdout}\n{completed.stderr}"
        )
    return completed


def pinned_ref() -> str:
    text = CONTAINERFILE.read_text(encoding="utf-8")
    match = re.search(
        r"^ARG CODEX_DESKTOP_LINUX_REF=([0-9a-f]{40})$",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError("Containerfile must pin a 40-character wrapper commit")
    return match.group(1)


class CodexDesktopLinuxPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = pinned_ref()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.upstream = pathlib.Path(cls.temporary.name) / "codex-desktop-linux"
        cls.upstream.mkdir()
        source = os.environ.get("CODEX_DESKTOP_LINUX_SOURCE") or UPSTREAM_URL
        run(["git", "init", "."], cwd=cls.upstream)
        run(["git", "remote", "add", "origin", source], cwd=cls.upstream)
        run(["git", "fetch", "--depth=1", "origin", cls.pin], cwd=cls.upstream)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=cls.upstream)
        head = run(["git", "rev-parse", "HEAD"], cwd=cls.upstream).stdout.strip()
        if head != cls.pin:
            raise AssertionError(f"expected pinned wrapper {cls.pin}, got {head}")
        run(
            ["git", "apply", "--check", "--whitespace=error-all", str(PATCH)],
            cwd=cls.upstream,
        )
        run(
            ["git", "apply", "--whitespace=error-all", str(PATCH)],
            cwd=cls.upstream,
        )
        cls.registry = (cls.upstream / REGISTRY).read_text(encoding="utf-8")
        cls.implementation = (cls.upstream / IMPLEMENTATION).read_text(
            encoding="utf-8"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_wrapper_revision_remains_pinned(self) -> None:
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn(f"CODEX_DESKTOP_LINUX_REF ?= {self.pin}", makefile)
        self.assertEqual(self.pin, "7d4049b68b17bc663b8a934326fefcaca99e8ceb")

    def test_extracted_app_descriptor_remains_registered(self) -> None:
        self.assertIn(f'id: "{DESCRIPTOR_ID}"', self.registry)
        self.assertIn("extractedAppPatch({", self.registry)
        self.assertIn(f"apply: {ASSET_CALLER}", self.registry)

    def test_assets_caller_is_reachable_from_production_registry(self) -> None:
        self.assertIn(ASSET_CALLER, self.registry)
        self.assertRegex(
            self.registry,
            rf"apply:\s*{re.escape(ASSET_CALLER)}",
        )
        self.assertIn(f"function {ASSET_CALLER}", self.implementation)
        self.assertRegex(
            self.implementation,
            rf"module\.exports\s*=[\s\S]*{re.escape(ASSET_CALLER)}",
        )

    def test_trusted_client_hash_logic_remains_present(self) -> None:
        self.assertIn(
            "function codexLinuxTrustedBrowserClientSha256s",
            self.implementation,
        )
        self.assertIn(
            "=codexLinuxTrustedBrowserClientSha256s(",
            self.implementation,
        )
        self.assertIn("trustedBrowserClientSha256s", self.implementation)
        self.assertIn(
            'return source.includes("trustedBrowserClientSha256s")',
            self.implementation,
        )

    def test_automatic_javascript_approval_insertion_is_absent(self) -> None:
        self.assertNotIn("mcpServerConfigRegex", self.implementation)
        self.assertNotIn("mcpServerConfigAlreadyApprovedRegex", self.implementation)
        self.assertNotIn("patchedAnyMcpServerConfig", self.implementation)
        self.assertNotIn("approval_mode", self.implementation)
        self.assertNotRegex(
            self.implementation,
            re.compile(
                r"tools\s*:\s*\{\s*js\s*:\s*\{\s*approval_mode\s*:\s*"
                r"[\"'`]approve[\"'`]"
            ),
        )
        self.assertNotIn("skipping node_repl approval patch", self.implementation)

    def test_unrelated_wrapper_patches_remain_enabled(self) -> None:
        enabled_ids = set(re.findall(r'id: "([^"]+)"', self.registry))
        self.assertTrue(UNRELATED_IDS.issubset(enabled_ids))
        self.assertIn("applyLinuxBrowserUseRouteLivenessPatch", self.registry)
        self.assertIn("applyLinuxBrowserUseSocketDirectoryPatch", self.registry)

    def test_container_build_applies_patch_strictly_before_install(self) -> None:
        text = CONTAINERFILE.read_text(encoding="utf-8")
        copy_index = text.index(str(PATCH.relative_to(ROOT)))
        check_index = text.index("git apply --check --whitespace=error-all")
        apply_index = text.index("git apply --whitespace=error-all")
        install_index = text.index("./install.sh --fresh")
        verify_index = text.index(
            "python3 /usr/local/libexec/grotto-verify-installed-chatgpt-policy"
        )
        self.assertLess(copy_index, check_index)
        self.assertLess(check_index, apply_index)
        self.assertLess(apply_index, install_index)
        self.assertLess(install_index, verify_index)
        self.assertNotIn("git apply --reject", text)
        self.assertNotIn("git apply --3way", text)
        self.assertNotIn("|| true", text[text.index("git apply --check"):install_index])


if __name__ == "__main__":
    unittest.main()
