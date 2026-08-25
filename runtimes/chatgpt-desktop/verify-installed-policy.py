#!/usr/bin/python3
"""Record Node REPL and Browser Use policy for the installed ChatGPT package.

Grotto used to build ChatGPT Desktop from a community wrapper that repacked the
macOS DMG, and this script verified that Grotto's own patches to that wrapper
had survived the rebuild. The image now installs OpenAI's native Linux package
and applies no patches to it, so the question changed: instead of proving a
local edit is still in place, this reports what the vendor bundle actually
exposes, and refuses to produce a manifest when the bundle carries a policy
Grotto will not ship.

The one hard failure is unattended JavaScript execution: a bundle that approves
`node_repl` JavaScript without asking the user fails the build rather than
being recorded as a finding.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA_VERSION = 2
VERIFICATION_SOURCE = "installed-vendor-package"
PACKAGE_NAME = "chatgpt"
JAVASCRIPT_SUFFIXES = {".js", ".cjs", ".mjs"}
ASAR_NAME = "app.asar"
# Read the archive in windows rather than whole: app.asar is a few hundred
# megabytes. Overlap consecutive windows so a match cannot be split across the
# boundary and missed.
SCAN_WINDOW_BYTES = 8 * 1024 * 1024
SCAN_OVERLAP_BYTES = 64 * 1024

# Property names may be quoted and production bundles are minified. Keep this
# structural instead of relying on one source whitespace layout.
AUTO_APPROVAL_RE = re.compile(
    rb"[\"'`]?tools[\"'`]?\s*:\s*\{[^{}]{0,512}"
    rb"[\"'`]?js[\"'`]?\s*:\s*\{[^{}]{0,512}"
    rb"[\"'`]?approval_mode[\"'`]?\s*:\s*[\"'`]approve[\"'`]",
    re.DOTALL,
)
NODE_REPL_MARKERS = (
    b"nodeReplPath",
    b"node_repl",
)
BROWSER_USE_MARKERS = (
    b"browser-client.mjs",
    b"browser_use",
)


class VerificationError(RuntimeError):
    """The installed application could not be classified safely."""


def scannable_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Every file that can carry application JavaScript.

    Loose scripts and the packed asar archive are both plain text as far as
    these markers are concerned, so the archive is scanned as bytes instead of
    being unpacked.
    """
    if not root.is_dir():
        raise VerificationError(f"installed application root is missing: {root}")
    files = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file()
        and (
            candidate.suffix.lower() in JAVASCRIPT_SUFFIXES
            or candidate.name == ASAR_NAME
        )
    )
    if not any(candidate.name == ASAR_NAME for candidate in files):
        raise VerificationError(f"no {ASAR_NAME} archive found below {root}")
    return files


def scan(files: list[pathlib.Path]) -> tuple[list[str], set[bytes], set[bytes]]:
    """Return auto-approval hits plus the markers each family matched."""
    auto_approved: list[str] = []
    node_repl: set[bytes] = set()
    browser_use: set[bytes] = set()

    for path in files:
        try:
            with path.open("rb") as handle:
                carry = b""
                while True:
                    block = handle.read(SCAN_WINDOW_BYTES)
                    if not block:
                        break
                    window = carry + block
                    if AUTO_APPROVAL_RE.search(window):
                        auto_approved.append(str(path))
                    node_repl.update(
                        marker for marker in NODE_REPL_MARKERS if marker in window
                    )
                    browser_use.update(
                        marker for marker in BROWSER_USE_MARKERS if marker in window
                    )
                    carry = window[-SCAN_OVERLAP_BYTES:]
        except OSError as exc:
            raise VerificationError(f"cannot inspect {path}: {exc}") from exc

    return sorted(set(auto_approved)), node_repl, browser_use


def installed_package(expected_version: str) -> dict[str, str]:
    """Read the package identity dpkg recorded, not what the build asked for."""
    try:
        completed = subprocess.run(
            [
                "dpkg-query",
                "--show",
                "--showformat=${Package}\\n${Version}\\n${Architecture}\\n${Status}",
                PACKAGE_NAME,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"cannot query the installed package: {exc}") from exc
    if completed.returncode != 0:
        raise VerificationError(
            f"package {PACKAGE_NAME} is not installed: "
            f"{completed.stderr.strip() or completed.returncode}"
        )

    fields = completed.stdout.split("\n")
    if len(fields) != 4:
        raise VerificationError("dpkg returned an unreadable package record")
    name, version, architecture, status = (field.strip() for field in fields)
    if status != "install ok installed":
        raise VerificationError(f"package {name} is not fully installed: {status}")
    if version != expected_version:
        raise VerificationError(
            f"installed {name} version {version} does not match the pinned "
            f"build version {expected_version}"
        )
    return {"name": name, "version": version, "architecture": architecture}


def build_manifest(root: pathlib.Path, expected_version: str) -> dict[str, object]:
    package = installed_package(expected_version)
    files = scannable_files(root)
    auto_approved, node_repl, browser_use = scan(files)

    if auto_approved:
        raise VerificationError(
            "Node REPL JavaScript automatic approval is present in installed "
            "bundle(s): " + ", ".join(auto_approved)
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": VERIFICATION_SOURCE,
        "package": package,
        "node_repl": {
            "exposed": bool(node_repl),
            "auto_approved": False,
            "verified": True,
            "verification_source": VERIFICATION_SOURCE,
        },
        "browser_use": {
            "present": bool(browser_use),
            # The vendor ships and signs its own Browser Use clients, so there
            # is no repacked client for Grotto to re-trust. The field stays so
            # grotto-doctor keeps reporting a stable shape across the change.
            "trusted_client_hash_patch": False,
            "verified": True,
        },
        "files_scanned": len(files),
    }


def write_manifest(path: pathlib.Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        manifest = build_manifest(arguments.root, arguments.package_version)
        write_manifest(arguments.manifest, manifest)
    except VerificationError as exc:
        print(f"installed ChatGPT policy verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
