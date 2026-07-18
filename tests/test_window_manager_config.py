#!/usr/bin/env python3
"""Validate the Openbox and Labwc single-application window policies."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIGURATOR = Path(
    os.environ.get(
        "GROTTO_WINDOW_CONFIGURATOR",
        REPOSITORY
        / "runtimes/chatgpt-desktop/root/usr/local/libexec/grotto-configure-openbox",
    )
)
LABWC_CONFIG = Path(
    os.environ.get(
        "GROTTO_LABWC_CONFIG",
        REPOSITORY / "runtimes/chatgpt-desktop/root/defaults/labwc.xml",
    )
)


def local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def child_settings(rule: ET.Element) -> dict[str, str]:
    return {
        local_name(child.tag): (child.text or "").strip()
        for child in rule
        if isinstance(child.tag, str) and local_name(child.tag) != "action"
    }


def actions(rule: ET.Element) -> list[str]:
    return [
        child.attrib.get("name", "")
        for child in rule
        if local_name(child.tag) == "action"
    ]


def parse_rules(config: Path, section_name: str, rule_name: str) -> list[ET.Element]:
    root = ET.parse(config).getroot()
    section = next(
        child for child in root if local_name(child.tag) == section_name
    )
    return [
        child for child in section if local_name(child.tag) == rule_name
    ]


def assert_openbox_policy(config: Path) -> None:
    rules = parse_rules(config, "applications", "application")
    assert not any(
        rule.attrib == {"class": "*"}
        and child_settings(rule).get("maximized") == "yes"
        for rule in rules
    ), "Selkies catch-all maximization must be removed"

    main = [
        rule
        for rule in rules
        if rule.attrib.get("class") == "codex-desktop"
        and rule.attrib.get("role") == "browser-window"
        and rule.attrib.get("type") == "normal"
    ]
    assert len(main) == 1
    assert child_settings(main[0]) == {
        "decor": "no",
        "focus": "no",
        "layer": "below",
        "fullscreen": "no",
        "maximized": "yes",
    }

    for window_type in ("dialog", "utility"):
        popup = [
            rule
            for rule in rules
            if rule.attrib.get("class") == "*"
            and rule.attrib.get("type") == window_type
        ]
        assert len(popup) == 1
        assert child_settings(popup[0]) == {
            "decor": "yes",
            "focus": "yes",
            "layer": "above",
            "fullscreen": "no",
            "maximized": "no",
        }


def assert_labwc_policy(config: Path) -> None:
    rules = parse_rules(config, "windowRules", "windowRule")
    assert not any(
        rule.attrib.get("identifier") == "*"
        and "Maximize" in actions(rule)
        for rule in rules
    ), "Labwc must not maximize every window"

    main = [
        rule
        for rule in rules
        if rule.attrib.get("identifier") == "codex-desktop"
        and rule.attrib.get("title") == "ChatGPT"
        and rule.attrib.get("type") == "normal"
    ]
    assert len(main) == 1
    assert "matchOnce" not in main[0].attrib
    assert main[0].attrib.get("serverDecoration") == "no"
    assert child_settings(main[0]).get("ignoreFocusRequest") == "yes"
    assert actions(main[0]) == ["Maximize", "Lower", "ToggleAlwaysOnBottom"]

    for window_type in ("dialog", "utility"):
        popup = [rule for rule in rules if rule.attrib.get("type") == window_type]
        assert len(popup) == 1
        assert popup[0].attrib.get("serverDecoration") == "yes"
        assert child_settings(popup[0]).get("ignoreFocusRequest") == "no"
        assert actions(popup[0]) == [
            "UnMaximize",
            "ToggleAlwaysOnTop",
            "Raise",
            "Focus",
        ]


def load_configurator():
    loader = importlib.machinery.SourceFileLoader(
        "grotto_configure_openbox",
        str(CONFIGURATOR),
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main() -> None:
    configurator = load_configurator()
    fixture = """<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications>
    <application class="*"><maximized>yes</maximized></application>
  </applications>
</openbox_config>
"""
    with tempfile.TemporaryDirectory() as temporary_directory:
        fixture_path = Path(temporary_directory) / "rc.xml"
        fixture_path.write_text(fixture, encoding="utf-8")
        configurator.configure_openbox(fixture_path)
        configurator.configure_openbox(fixture_path)
        assert_openbox_policy(fixture_path)

    actual_openbox = os.environ.get("GROTTO_OPENBOX_CONFIG")
    if actual_openbox:
        assert_openbox_policy(Path(actual_openbox))
    assert_labwc_policy(LABWC_CONFIG)
    print("window-manager policy tests passed")


if __name__ == "__main__":
    main()
