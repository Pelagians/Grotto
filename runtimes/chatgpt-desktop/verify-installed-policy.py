#!/usr/bin/python3
"""Verify Browser Use and Node REPL policy in an installed Electron application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterable

SCHEMA_VERSION = 1
VERIFICATION_SOURCE = "installed-electron-bundle"
JAVASCRIPT_SUFFIXES = {".js", ".cjs", ".mjs"}
BROWSER_CLIENT_SUFFIXES = {
    "browser": pathlib.PurePath(
        "resources/plugins/openai-bundled/plugins/browser/scripts/browser-client.mjs"
    ).parts,
    "chrome": pathlib.PurePath(
        "resources/plugins/openai-bundled/plugins/chrome/scripts/browser-client.mjs"
    ).parts,
}

# Property names may be quoted and production bundles may be minified. Keep this
# structural instead of relying on one source whitespace layout.
AUTO_APPROVAL_RE = re.compile(
    r"[\"'`]?tools[\"'`]?\s*:\s*\{[^{}]{0,512}"
    r"[\"'`]?js[\"'`]?\s*:\s*\{[^{}]{0,512}"
    r"[\"'`]?approval_mode[\"'`]?\s*:\s*[\"'`]approve[\"'`]",
    re.DOTALL,
)
TRUST_HELPER_DEFINITION_RE = re.compile(
    r"function\s+codexLinuxTrustedBrowserClientSha256s\s*\("
)
TRUST_HELPER_APPLICATION_RE = re.compile(
    r"(?:"
    r"[A-Za-z_$][\w$]*\s*=\s*codexLinuxTrustedBrowserClientSha256s\s*\("
    r"|\.transform\(\s*codexLinuxTrustedBrowserClientSha256s\s*\)"
    r")"
)
TRUSTED_HASH_LITERAL_RE = re.compile(
    r"(?:const|let|var)?\s*__codexLinuxBundledBrowserClientSha256s\s*=\s*"
    r"(\[(?:\s*[\"'][0-9a-f]{64}[\"']\s*,?){2}\])"
)
NODE_REPL_MARKERS = (
    "nodeReplPath",
    "mcp_servers.${",
    "startup_timeout_sec:120",
)
BROWSER_USE_MARKERS = (
    "trustedBrowserClientSha256s",
    "plugins/openai-bundled/plugins/browser/scripts/browser-client.mjs",
    "plugins`, `openai-bundled`, `plugins`, __codexPluginName",
)
AMBIGUOUS_MARKERS = (
    "node_repl",
    "node-repl",
    "trustedBrowserClientSha256s",
    "browser-client.mjs",
)


class VerificationError(RuntimeError):
    """The installed application could not be classified safely."""


@dataclass(frozen=True)
class Inspection:
    node_repl_exposed: bool
    node_repl_auto_approved: bool
    browser_use_trusted_client_hash_patch: bool
    files_scanned: int

    def manifest(self, wrapper_revision: str) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "wrapper_revision": wrapper_revision,
            "node_repl": {
                "exposed": self.node_repl_exposed,
                "auto_approved": self.node_repl_auto_approved,
                "verified": True,
                "verification_source": VERIFICATION_SOURCE,
            },
            "browser_use": {
                "trusted_client_hash_patch": (
                    self.browser_use_trusted_client_hash_patch
                ),
                "verified": True,
            },
        }


def javascript_files(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.is_dir():
        raise VerificationError(f"installed application root is missing: {root}")
    files = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in JAVASCRIPT_SUFFIXES
    )
    if not files:
        raise VerificationError(f"no JavaScript bundles found below {root}")
    return files


def read_sources(files: Iterable[pathlib.Path]) -> list[tuple[pathlib.Path, str]]:
    result: list[tuple[pathlib.Path, str]] = []
    for path in files:
        try:
            result.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError) as exc:
            raise VerificationError(f"cannot inspect JavaScript bundle {path}: {exc}") from exc
    return result


def has_path_suffix(path: pathlib.Path, suffix: tuple[str, ...]) -> bool:
    return len(path.parts) >= len(suffix) and path.parts[-len(suffix) :] == suffix


def installed_browser_client_hashes(
    sources: Iterable[tuple[pathlib.Path, str]],
) -> dict[str, str]:
    matches: dict[str, list[pathlib.Path]] = {
        plugin: [] for plugin in BROWSER_CLIENT_SUFFIXES
    }
    for path, _source in sources:
        for plugin, suffix in BROWSER_CLIENT_SUFFIXES.items():
            if has_path_suffix(path, suffix):
                matches[plugin].append(path)

    present = {plugin: paths for plugin, paths in matches.items() if paths}
    if not present:
        return {}
    if any(len(matches[plugin]) != 1 for plugin in BROWSER_CLIENT_SUFFIXES):
        detail = ", ".join(
            f"{plugin}={len(paths)}" for plugin, paths in sorted(matches.items())
        )
        raise VerificationError(
            f"Browser Use client artifact structure is incomplete or ambiguous: {detail}"
        )

    return {
        plugin: hashlib.sha256(paths[0].read_bytes()).hexdigest()
        for plugin, paths in matches.items()
    }


def embedded_trusted_hashes(combined: str) -> set[str] | None:
    matches = TRUSTED_HASH_LITERAL_RE.findall(combined)
    if not matches:
        return None
    if len(matches) != 1:
        raise VerificationError(
            "Browser Use trusted-client hash literal is duplicated or ambiguous"
        )
    try:
        values = json.loads(matches[0].replace("'", '"'))
    except json.JSONDecodeError as exc:
        raise VerificationError(
            "Browser Use trusted-client hash literal is malformed"
        ) from exc
    if (
        not isinstance(values, list)
        or len(values) != 2
        or len(set(values)) != 2
        or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in values)
    ):
        raise VerificationError(
            "Browser Use trusted-client hash literal is incomplete or contradictory"
        )
    return set(values)


def inspect_installed_application(root: pathlib.Path) -> Inspection:
    files = javascript_files(root)
    sources = read_sources(files)

    unsafe_paths = [
        str(path) for path, source in sources if AUTO_APPROVAL_RE.search(source)
    ]
    node_repl_auto_approved = bool(unsafe_paths)
    if node_repl_auto_approved:
        raise VerificationError(
            "Node REPL JavaScript automatic approval remains in installed bundle(s): "
            + ", ".join(unsafe_paths)
        )

    combined = "\n".join(source for _path, source in sources)
    helper_definition = bool(TRUST_HELPER_DEFINITION_RE.search(combined))
    helper_application = bool(TRUST_HELPER_APPLICATION_RE.search(combined))
    node_repl_markers = {marker for marker in NODE_REPL_MARKERS if marker in combined}
    browser_use_markers = {marker for marker in BROWSER_USE_MARKERS if marker in combined}
    ambiguous_markers = {marker for marker in AMBIGUOUS_MARKERS if marker in combined}
    client_hashes = installed_browser_client_hashes(sources)
    embedded_hashes = embedded_trusted_hashes(combined)

    node_repl_exposed = bool(node_repl_markers)
    dynamic_hash_helper = all(
        marker in combined
        for marker in (
            "createHash",
            "sha256",
            "readFileSync",
            "browser-client.mjs",
            "codexLinuxTrustedBrowserClientSha256s",
        )
    )
    exact_literal_hashes = (
        bool(client_hashes)
        and embedded_hashes is not None
        and embedded_hashes == set(client_hashes.values())
    )
    if embedded_hashes is not None and client_hashes:
        if embedded_hashes != set(client_hashes.values()):
            raise VerificationError(
                "embedded Browser Use trusted-client hashes do not match the installed clients"
            )
    trusted_hash_behavior = (
        helper_definition
        and helper_application
        and (dynamic_hash_helper or exact_literal_hashes)
    )
    browser_use_present = bool(
        browser_use_markers
        or client_hashes
        or helper_definition
        or helper_application
        or embedded_hashes
    )

    if helper_definition != helper_application:
        raise VerificationError("Browser Use trusted-client helper is only partially installed")
    if browser_use_present:
        if not client_hashes:
            raise VerificationError(
                "Browser Use markers exist but both installed client artifacts are not present"
            )
        if not trusted_hash_behavior:
            evidence = sorted(browser_use_markers) + sorted(client_hashes)
            raise VerificationError(
                "Browser Use is present without a verified trusted-client hash adjustment"
                + (f" (evidence: {', '.join(evidence)})" if evidence else "")
            )
        if not node_repl_exposed:
            raise VerificationError(
                "Browser Use runtime exists but Node REPL integration cannot be classified"
            )
    elif node_repl_exposed or ambiguous_markers:
        markers = sorted(ambiguous_markers | node_repl_markers)
        raise VerificationError(
            "installed bundle contains ambiguous Browser Use/Node REPL markers: "
            + ", ".join(markers)
        )

    return Inspection(
        node_repl_exposed=node_repl_exposed,
        node_repl_auto_approved=node_repl_auto_approved,
        browser_use_trusted_client_hash_patch=(
            browser_use_present and trusted_hash_behavior
        ),
        files_scanned=len(files),
    )


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
    parser.add_argument("--wrapper-revision", required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inspection = inspect_installed_application(arguments.root)
        manifest = inspection.manifest(arguments.wrapper_revision)
        write_manifest(arguments.manifest, manifest)
    except VerificationError as exc:
        print(f"installed ChatGPT policy verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
