#!/usr/bin/env python3
"""Print bounded structural contexts for Claude's current titlebar source."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys

TERMS = (
    b"titleBarStyle",
    b"titleBarOverlay",
    b"setTitleBarOverlay",
    b"BrowserWindow",
    b"autoHideMenuBar",
)
CONTEXT_RADIUS = 180
MAX_MATCHES_PER_TERM = 3


def load_patcher(path: Path):
    loader = importlib.machinery.SourceFileLoader("grotto_claude_titlebar_patcher", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"Unable to load patcher: {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def sanitize(raw: bytes) -> str:
    return (
        raw.decode("utf-8", errors="replace")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: inspect <patcher> <app.asar>", file=sys.stderr)
        return 64

    patcher = load_patcher(Path(sys.argv[1]))
    bundle = Path(sys.argv[2])
    header, data = patcher.read_asar(bundle)
    entry = patcher.locate_entry(header, patcher.TARGET_PATH)
    target = patcher.unpacked_target(bundle)
    source = target.read_bytes() if entry.get("unpacked") else patcher.packed_content(entry, data)

    print(json.dumps({"target": patcher.TARGET_PATH, "size": len(source)}))
    for term in TERMS:
        positions: list[int] = []
        start = 0
        while len(positions) < MAX_MATCHES_PER_TERM:
            index = source.find(term, start)
            if index < 0:
                break
            positions.append(index)
            start = index + len(term)

        contexts = []
        for index in positions:
            left = max(0, index - CONTEXT_RADIUS)
            right = min(len(source), index + len(term) + CONTEXT_RADIUS)
            contexts.append({"offset": index, "text": sanitize(source[left:right])})
        print(
            json.dumps(
                {
                    "term": term.decode("ascii"),
                    "count": source.count(term),
                    "contexts": contexts,
                },
                ensure_ascii=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
