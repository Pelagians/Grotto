#!/usr/bin/env python3
"""Validate the Openbox and Labwc single-application window policies."""

from __future__ import annotations

import argparse
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
LAUNCHER = REPOSITORY / (
    "runtimes/chatgpt-desktop/root/usr/local/bin/grotto-chatgpt-desktop"
)
INIT_SCRIPT = REPOSITORY / (
    "runtimes/chatgpt-desktop/root/custom-cont-init.d/10-grotto-chatgpt-permissions"
)
AUTOSTART = REPOSITORY / "runtimes/chatgpt-desktop/root/defaults/autostart"
FULLSCREEN_HELPER = REPOSITORY / (
    "runtimes/chatgpt-desktop/root/usr/local/libexec/grotto-chatgpt-fullscreen"
)
CONTAINERFILE = REPOSITORY / "Containerfile.chatgpt-desktop"
# The vendor package sets no Grotto-specific WM_CLASS, so the launcher passes
# --class and the window rules match that value.
WM_CLASS = "chatgpt-desktop"


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

    main_index = None
    for index, rule in enumerate(rules):
        if (
            rule.attrib.get("class") == WM_CLASS
            and rule.attrib.get("type") == "normal"
        ):
            assert main_index is None, "one main-surface rule only"
            main_index = index
    assert main_index is not None
    main = rules[main_index]
    # The application advertises no WM_WINDOW_ROLE, so a role match would never
    # select this window.
    assert "role" not in main.attrib
    # True fullscreen, not borderless maximization: the application resets its
    # own window bounds a few seconds after mapping, which undoes a maximized
    # rule on every start.
    assert child_settings(main) == {
        "decor": "no",
        "focus": "no",
        "layer": "below",
        "fullscreen": "yes",
        "maximized": "no",
    }

    # Openbox merges matching rules in document order, so the catch-all for
    # ordinary windows has to come before the rule that overrides it.
    general = [
        index
        for index, rule in enumerate(rules)
        if rule.attrib.get("class") == "*"
        and rule.attrib.get("type") == "normal"
    ]
    assert len(general) == 1
    assert general[0] < main_index
    assert child_settings(rules[general[0]]) == {
        "decor": "yes",
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
    assert not any(
        rule.attrib.get("identifier") == "*"
        and "Maximize" in actions(rule)
        for rule in rules
    ), "Labwc must not maximize every window"

    main = [
        rule
        for rule in rules
        if rule.attrib.get("identifier") == WM_CLASS
        and rule.attrib.get("type") == "normal"
    ]
    assert len(main) == 1
    assert "matchOnce" not in main[0].attrib
    # The window title follows the open conversation, so the rule must not
    # narrow itself to one title.
    assert "title" not in main[0].attrib
    assert main[0].attrib.get("serverDecoration") == "no"
    assert child_settings(main[0]).get("ignoreFocusRequest") == "yes"
    assert actions(main[0]) == [
        "ToggleFullscreen",
        "Lower",
        "ToggleAlwaysOnBottom",
    ]

    general = [
        rule
        for rule in rules
        if rule.attrib.get("identifier") == "*"
        and rule.attrib.get("type") == "normal"
    ]
    assert len(general) == 1
    assert general[0].attrib.get("serverDecoration") == "yes"

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


def assert_launcher_matches_window_rules() -> None:
    """The launcher and the window rules must agree on one WM class.

    Nothing at runtime reconciles them: if the launcher passes a class the
    rules do not match, the desktop silently comes up decorated and unmanaged.
    """
    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert (
        'CHATGPT_WM_CLASS="${GROTTO_CHATGPT_WM_CLASS:-' + WM_CLASS + '}"'
    ) in launcher
    assert '"--class=${CHATGPT_WM_CLASS}"' in launcher

    containerfile = CONTAINERFILE.read_text(encoding="utf-8")
    assert f"GROTTO_CHATGPT_WM_CLASS={WM_CLASS}" in containerfile

    configurator = CONFIGURATOR.read_text(encoding="utf-8")
    assert (
        f'os.environ.get("GROTTO_CHATGPT_WM_CLASS", "{WM_CLASS}")' in configurator
    )


def assert_primary_lane_is_wayland() -> None:
    """Wayland/Labwc is the primary lane, end to end.

    Selkies picks the session, the launcher picks the Chromium backend, and the
    Labwc policy is what actually holds the window. The two have to agree: with
    Selkies on Wayland but Chromium on X11 the app runs under XWayland and the
    Labwc rules never match it.
    """
    containerfile = CONTAINERFILE.read_text(encoding="utf-8")
    assert "PIXELFLUX_WAYLAND=true" in containerfile
    assert "ELECTRON_OZONE_PLATFORM_HINT=wayland" in containerfile

    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert '"${CODEX_OZONE_PLATFORM:-wayland}"' in launcher


def assert_wayland_fullscreen_is_repaired() -> None:
    """The Labwc rule alone does not hold this application fullscreen.

    It fullscreens the surface at map time and the application unsets it a few
    seconds later when it resets its own bounds, so the session has to
    re-request fullscreen once the application has settled.
    """
    helper = FULLSCREEN_HELPER.read_text(encoding="utf-8")
    # Must set the state, never toggle it: a retry against an already
    # fullscreen window would otherwise put it back in a corner.
    assert 'wlrctl toplevel fullscreen "app_id:${CHATGPT_WM_CLASS}"' in helper
    assert 'state:fullscreen' in helper
    # X11 needs no repair, and the helper must not run forever.
    assert 'if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then' in helper
    assert "APPEAR_TIMEOUT_SECONDS" in helper

    autostart = AUTOSTART.read_text(encoding="utf-8")
    assert "/usr/local/libexec/grotto-chatgpt-fullscreen &" in autostart

    containerfile = CONTAINERFILE.read_text(encoding="utf-8")
    assert "wlrctl" in containerfile


def assert_policy_is_reapplied_to_persistent_state() -> None:
    """Openbox reads the persistent copy, not the build-time one.

    A /config volume from an older image otherwise keeps a superseded policy,
    or LinuxServer's catch-all maximization, after an image update.
    """
    init_script = INIT_SCRIPT.read_text(encoding="utf-8")
    assert (
        "/usr/local/libexec/grotto-configure-openbox /config/.config/openbox/rc.xml"
        in init_script
    )
    assert "/config/.config/labwc/rc.xml" in init_script


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


def main(*, installed_image: bool = False) -> None:
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
    if not installed_image:
        assert_launcher_matches_window_rules()
        assert_primary_lane_is_wayland()
        assert_wayland_fullscreen_is_repaired()
        assert_policy_is_reapplied_to_persistent_state()
    print("window-manager policy tests passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--installed-image",
        action="store_true",
        help="skip repository-only client build-policy checks",
    )
    arguments = parser.parse_args()
    main(installed_image=arguments.installed_image)
