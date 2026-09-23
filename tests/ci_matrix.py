#!/usr/bin/env python3
"""Select affected images; unknown changes deliberately select the full matrix."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROWS = json.loads((ROOT / ".github/image-matrix.json").read_text())
ALL = {row["name"] for row in ROWS}


def select(paths):
    selected = set()
    for path in paths:
        if path.startswith("docs/") or path in {"README.md", "LICENSE"}:
            continue
        if path == "Containerfile":
            selected.add("grotto-openclaw")
        elif path.startswith("Containerfile."):
            name = "grotto-" + path.removeprefix("Containerfile.")
            if name == "grotto-openadapt-teach":
                selected.add(name)
            elif name in ALL:
                selected.add(name)
            else:
                return ALL
        elif path.startswith("runtimes/chatgpt-desktop/"):
            selected.add("grotto-chatgpt-desktop")
        elif path.startswith("runtimes/hermes-desktop/"):
            selected.add("grotto-hermes-desktop")
        elif path.startswith("runtimes/openadapt-teach/"):
            selected.add("grotto-openadapt-teach")
        elif path.startswith("runtimes/sports-workers/"):
            selected.update({"grotto-sports-market-probe", "grotto-sports-source-probe", "grotto-playnow-observer"})
        elif path.startswith("runtimes/sports-market-probe/"):
            selected.add("grotto-sports-market-probe")
        elif path.startswith("runtimes/sports-source-probe/"):
            selected.add("grotto-sports-source-probe")
        elif path.startswith("runtimes/playnow-observer/"):
            selected.add("grotto-playnow-observer")
        elif path.startswith("runtimes/"):
            return ALL
        elif path == "Brewfile" or path.startswith("files/"):
            selected.update({"grotto-openclaw", "grotto-hermes", "grotto-hermes-desktop"})
        elif path.startswith("quadlet/"):
            selected.update({"grotto-openclaw", "grotto-hermes"})
        else:
            # Tests, workflow definitions, build context rules, and unfamiliar
            # paths can affect more than one image. Fail open to full coverage.
            return ALL
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    if args.base and set(args.base) != {"0"}:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{args.base}...{args.head}"],
            text=True,
        ).splitlines()
        selected = select(changed)
    else:
        selected = ALL
    rows = [row for row in ROWS if row["name"] in selected]
    print(json.dumps({"include": rows}, separators=(",", ":")))


if __name__ == "__main__":
    main()
