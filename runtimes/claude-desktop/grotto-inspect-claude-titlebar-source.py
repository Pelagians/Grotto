#!/usr/bin/env python3
"""Print bounded structural contexts for Claude's current titlebar source."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterator

TERMS = (
    b"titleBarStyle",
    b"titleBarOverlay",
    b"setTitleBarOverlay",
    b"BrowserWindow",
    b"autoHideMenuBar",
    b"frame:",
)
TEXT_SUFFIXES = {".js", ".mjs", ".cjs", ".html", ".css"}
CONTEXT_RADIUS = 160
MAX_CONTEXTS_PER_FILE = 3
MAX_CANDIDATES = 30
MAX_FILE_SIZE = 64 * 1024 * 1024


def load_patcher(path: Path):
    loader = importlib.machinery.SourceFileLoader("grotto_claude_titlebar_patcher", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"Unable to load patcher: {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def walk_entries(files: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    for name, raw_entry in files.items():
        if not isinstance(raw_entry, dict):
            continue
        path = f"{prefix}/{name}" if prefix else name
        children = raw_entry.get("files")
        if isinstance(children, dict):
            yield from walk_entries(children, path)
        else:
            yield path, raw_entry


def sanitize(raw: bytes) -> str:
    return (
        raw.decode("utf-8", errors="replace")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )


def entry_content(patcher, bundle: Path, entry: dict[str, Any], path: str, data: bytes) -> bytes:
    if entry.get("unpacked"):
        return (Path(f"{bundle}.unpacked") / path).read_bytes()
    return patcher.packed_content(entry, data)


def contexts_for(source: bytes, term: bytes) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    start = 0
    while len(contexts) < MAX_CONTEXTS_PER_FILE:
        index = source.find(term, start)
        if index < 0:
            break
        left = max(0, index - CONTEXT_RADIUS)
        right = min(len(source), index + len(term) + CONTEXT_RADIUS)
        contexts.append({"offset": index, "text": sanitize(source[left:right])})
        start = index + len(term)
    return contexts


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: inspect <patcher> <app.asar>", file=sys.stderr)
        return 64

    patcher = load_patcher(Path(sys.argv[1]))
    bundle = Path(sys.argv[2])
    header, data = patcher.read_asar(bundle)

    candidates = 0
    for path, entry in walk_entries(header["files"]):
        if Path(path).suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            size = int(entry.get("size", 0))
        except (TypeError, ValueError):
            continue
        if size <= 0 or size > MAX_FILE_SIZE:
            continue

        source = entry_content(patcher, bundle, entry, path, data)
        counts = {term.decode("ascii"): source.count(term) for term in TERMS}
        counts = {term: count for term, count in counts.items() if count}
        if not counts:
            continue

        preferred_term = next(
            (
                term
                for term in TERMS
                if term.decode("ascii") in counts
                and term not in {b"BrowserWindow", b"frame:"}
            ),
            next(term for term in TERMS if term.decode("ascii") in counts),
        )
        print(
            json.dumps(
                {
                    "path": path,
                    "size": len(source),
                    "counts": counts,
                    "contexts": contexts_for(source, preferred_term),
                },
                ensure_ascii=True,
            )
        )
        candidates += 1
        if candidates >= MAX_CANDIDATES:
            break

    print(json.dumps({"candidateCount": candidates}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
