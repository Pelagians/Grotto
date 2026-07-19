#!/usr/bin/env python3
"""Print bounded titlebar contexts from Claude's current ASAR chunks."""

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
)
TEXT_SUFFIXES = {".js", ".mjs", ".cjs"}
CONTEXT_RADIUS = 260
MAX_CONTEXTS_PER_TERM = 4
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
    while len(contexts) < MAX_CONTEXTS_PER_TERM:
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

    candidate_count = 0
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
        term_results = []
        for term in TERMS:
            count = source.count(term)
            if count:
                term_results.append(
                    {
                        "term": term.decode("ascii"),
                        "count": count,
                        "contexts": contexts_for(source, term),
                    }
                )
        if not term_results:
            continue

        print(
            json.dumps(
                {
                    "path": path,
                    "size": len(source),
                    "terms": term_results,
                },
                ensure_ascii=True,
            )
        )
        candidate_count += 1

    print(json.dumps({"candidateCount": candidate_count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
