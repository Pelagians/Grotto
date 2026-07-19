#!/usr/bin/env python3
"""Validate Claude Desktop Openbox and Labwc window policies."""

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
        "GROTTO_CLAUDE_WINDOW_CONFIGURATOR",
        REPOSITORY
        / "runtimes/claude-desktop/root/usr/local/libexec/grotto-configure-openbox",
    )
)
LABWC_CONFIG = Path(
    os.environ.get(
        "GROTTO_CLAUDE_LABWC_CONFIG",
        REPOSITORY / "runtimes/claude-desktop/root/defaults/labwc.xml",
    )
)
MAIN_IDENTIFIERS = {"com.anthropic.Claude", "claude-desktop"}


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

    mains = [
        rule
        for rule in rules
        if rule.attrib.get("class") in MAIN_IDENTIFIERS
        and rule.attrib.get("name") == "Claude*"
        and rule.attrib.get("type") == "normal"
    ]
    assert {rule.attrib["class"] for rule in mains} == MAIN_IDENTIFIERS
    for main in mains:
        assert child_settings(main) == {
            "decor": "no",
            "focus": "no",
            "layer": "below",
            "fullscreen": "yes",
            "maximized": "no",
        }

    firefox = [
        rule
        for rule in rules
        if rule.attrib.get("class") == "firefox*"
        and rule.attrib.get("type") == "normal"
    ]
    assert len(firefox) == 1
    assert child_settings(firefox[0]) == {
        "decor": "no",
        "focus": "yes",
        "layer": "above",
        "fullscreen": "no",
        "maximized": "no",
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

    mains = [
        rule
        for rule in rules
        if rule.attrib.get("identifier") in MAIN_IDENTIFIERS
        and rule.attrib.get("title") == "Claude*"
        and rule.attrib.get("type") == "normal"
    ]
    assert {rule.attrib["identifier"] for rule in mains} == MAIN_IDENTIFIERS
    for main in mains:
        assert main.attrib.get("serverDecoration") == "no"
        assert child_settings(main).get("ignoreFocusRequest") == "yes"
        assert actions(main) == [
            "ToggleFullscreen",
            "Lower",
            "ToggleAlwaysOnBottom",
        ]

    firefox_rules = [
        rule
        for rule in rules
        if rule.attrib.get("identifier") in {"firefox*", "org.mozilla.firefox*"}
        and rule.attrib.get("type") == "normal"
    ]
    assert len(firefox_rules) == 2
    for firefox in firefox_rules:
        assert firefox.attrib.get("serverDecoration") == "no"
        assert child_settings(firefox).get("ignoreFocusRequest") == "no"
        assert actions(firefox) == [
            "UnMaximize",
            "ToggleAlwaysOnTop",
            "Raise",
            "Focus",
        ]

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
        "grotto_claude_configure_openbox",
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

    actual_openbox = os.environ.get("GROTTO_CLAUDE_OPENBOX_CONFIG")
    if actual_openbox:
        assert_openbox_policy(Path(actual_openbox))
    assert_labwc_policy(LABWC_CONFIG)
    print("Claude window-manager policy tests passed")


if __name__ == "__main__":
    main()
