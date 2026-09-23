#!/usr/bin/env python3
"""Static contract checks for the Grotto Hermes image."""
import re
import os
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTAINERFILE = ROOT / "Containerfile.hermes"
HOOK = ROOT / "files/grotto-agent-entrypoint"
SMOKE = ROOT / "tests/smoke-hermes.sh"
DESKTOP_CONTAINERFILE = ROOT / "Containerfile.hermes-desktop"
DESKTOP_AUTOSTART = ROOT / "runtimes/hermes-desktop/root/defaults/autostart_wayland"
DESKTOP_CONSUMER = ROOT / "runtimes/hermes-desktop/root/usr/local/bin/pelagian-shell-consumer"
DESKTOP_INIT = ROOT / "runtimes/hermes-desktop/root/custom-cont-init.d/30-grotto-hermes-desktop"
DESKTOP_SESSION = ROOT / "runtimes/hermes-desktop/root/usr/local/bin/grotto-hermes-desktop-session"
DESKTOP_SMOKE = ROOT / "tests/smoke-hermes-desktop.sh"
DESKTOP_IMAGE_SMOKE = ROOT / "tests/hermes-desktop-image-smoke.sh"
DESKTOP_DOCS = ROOT / "docs/hermes-desktop.md"
WORKFLOW = ROOT / ".github/workflows/build.yml"
SHELL_IMAGE = (
    "ghcr.io/pelagians/pelagian-shell@sha256:"
    "5ad8e46d11bac94a5f7202c0f4cee5872f2f731b8602bac42329d42717d65122"
)


def workflow_step(workflow: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    start = workflow.index(marker)
    end = workflow.find("\n      - name: ", start + len(marker))
    return workflow[start:] if end == -1 else workflow[start:end]


def active_lines(block: str) -> set[str]:
    return {
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def main() -> None:
    image = CONTAINERFILE.read_text()
    hook = HOOK.read_text()
    smoke = SMOKE.read_text()
    assert "docker.io/nousresearch/hermes-agent:v2026.8.27@sha256:" in image
    assert 'VOLUME ["/opt/data", "/workspace", "/tools", "/home/linuxbrew/.linuxbrew", "/cache"]' in image
    assert "EXPOSE 8642 9119" in image
    assert "USER hermes" in image and "USER root" in image
    assert "/etc/cont-init.d/10-grotto-agent-environment" in image
    assert "supervisord" not in image and "hermes-webui" not in image
    assert "brew bundle --file=/usr/share/grotto/Brewfile" in image
    assert "chown -R hermes:hermes" not in hook
    assert "rm -rf /home/linuxbrew/.linuxbrew" not in hook
    assert "/cache/homebrew" in hook and "chown hermes:hermes" in hook
    assert "chown -R hermes:hermes" not in smoke
    assert "brew install hello" in smoke
    assert "! pgrep -f '[h]ermes-webui'" in smoke
    assert "run_name-recreated" in smoke

    desktop_image = DESKTOP_CONTAINERFILE.read_text()
    assert not DESKTOP_AUTOSTART.exists()
    desktop_consumer = DESKTOP_CONSUMER.read_text()
    desktop_init = DESKTOP_INIT.read_text()
    desktop_session = DESKTOP_SESSION.read_text()
    desktop_smoke = (ROOT / "tests/smoke-desktop.sh").read_text()
    desktop_smoke_lines = active_lines(desktop_smoke)
    desktop_docs = DESKTOP_DOCS.read_text()
    workflow = WORKFLOW.read_text()
    chatgpt_image = (ROOT / "Containerfile.chatgpt-desktop").read_text()
    chatgpt_launcher = (
        ROOT / "runtimes/chatgpt-desktop/root/usr/local/bin/grotto-chatgpt-desktop"
    ).read_text()
    chatgpt_policy = (ROOT / "runtimes/chatgpt-desktop/verify-installed-policy.py").read_text()
    bind_smoke = (ROOT / "tests/smoke-desktop-bind-mount.sh").read_text()
    assert not (
        ROOT
        / "runtimes/chatgpt-desktop/root/usr/local/libexec/grotto-configure-openbox"
    ).exists()
    assert not (ROOT / "tests/test_window_manager_config.py").exists()
    for containerfile in (desktop_image, chatgpt_image):
        assert re.findall(r"^ARG PELAGIAN_SHELL_IMAGE=(\S+)$", containerfile, re.M) == [
            SHELL_IMAGE
        ]
    assert "5fc308a70719a83cccdbba4c0e39c23f5a8239d5" in desktop_image
    shell_adapter_patch = (ROOT / "patches/hermes-desktop/pelagian-shell-window-chrome.patch").read_text()
    assert "applyPelagianShellWindowChrome" in shell_adapter_patch
    assert "hermes:window-chrome-policy" in shell_adapter_patch
    assert "windowChromePolicy === 'server'" in shell_adapter_patch
    assert shell_adapter_patch.count("role: 'dialog'") == 3
    assert shell_adapter_patch.count(
        "parent: mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined"
    ) == 3
    assert "HERMES_DESKTOP_WINDOW_CHROME_REPORT" in shell_adapter_patch
    assert "data-hermes-custom-titlebar" in shell_adapter_patch
    assert "data-hermes-window-chrome-control-cluster" in shell_adapter_patch
    assert "verify_hermes_window_chrome" in (ROOT / "tests/smoke-desktop.sh").read_text()
    assert "pelagian-shell-contract" in desktop_image
    assert "/usr/share/pelagian-shell/integrations/electron/window-chrome.mjs" in desktop_image
    assert "check-electron-chrome.py" in desktop_image
    assert "smoke-desktop-bind-mount.sh" in (ROOT / ".github/workflows/build.yml").read_text()
    assert "node:22-bookworm@sha256:8a34c4ab3ea2c5cd194f07e317b2a8f09461d3c8b05c4e34c8ccd56d56024c4d" in desktop_image
    assert "npm run builder -- --linux deb --publish never" in desktop_image
    assert "for attempt in 1 2 3" in desktop_image
    assert "npm ci" in desktop_image
    assert "pipefail" not in desktop_consumer
    assert "exec /usr/local/bin/grotto-hermes-desktop-session" in desktop_consumer
    assert "sh -n runtimes/hermes-desktop/root/usr/local/bin/pelagian-shell-consumer" in (ROOT / "Makefile").read_text()
    assert "HERMES_DESKTOP_USER_DATA_DIR=/config/hermes-desktop" in desktop_image
    assert "HERMES_DESKTOP_PASSWORD_STORE=gnome-libsecret" in desktop_image
    assert "HERMES_DESKTOP_DISABLE_GPU=1" in desktop_image
    assert 'VOLUME ["/config", "/workspace", "/tools", "/home/linuxbrew/.linuxbrew", "/cache"]' in desktop_image
    assert "/opt/data" not in desktop_image
    assert "secure-token-storage.json" in desktop_init
    assert '"on":true' in desktop_init
    assert "GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD" in desktop_session
    assert "gnome-keyring-daemon --unlock" in desktop_session
    assert "dbus-launch --sh-syntax" in desktop_session
    assert "dbus-run-session" not in desktop_session
    assert "session.log" in desktop_session
    assert "/config/hermes-desktop/session.log" in desktop_smoke
    assert "/config/hermes-desktop/hermes-home/logs/desktop.log" in desktop_smoke
    assert "exec /usr/local/bin/hermes-desktop" in desktop_session
    assert "--no-sandbox" in desktop_session
    assert "--enable-features=UseOzonePlatform" in desktop_session
    assert "--ozone-platform=wayland" in desktop_session
    assert "7feb586b1b1dc3c706afbb16a336c14092ac7d5a" in desktop_smoke
    assert "conformance/verify-shell-session.py" in desktop_smoke
    assert "conformance/start-shell-stream.sh" in desktop_smoke
    assert "--native" in desktop_smoke
    assert "--opaque-binary-env" in desktop_smoke
    assert "GROTTO_CHATGPT_AUTH_MODE=off" in desktop_smoke
    assert "--keyring" in desktop_smoke
    assert '"$engine" restart "$name"' in desktop_smoke
    assert "x11-utils" in desktop_image
    image_matrix = json.loads((ROOT / ".github/image-matrix.json").read_text())
    assert any(row["name"] == "grotto-hermes-desktop" and row["image"] == "ghcr.io/pelagians/grotto-hermes-desktop" for row in image_matrix)
    build_step = workflow_step(workflow, "Build candidate image")
    selector_step = workflow_step(workflow, "Select exact image under test")
    promote_step = workflow_step(workflow, "Promote qualified digest to release tags")
    chatgpt_step = workflow_step(workflow, "Probe ChatGPT Docker compatibility")
    hermes_step = workflow_step(workflow, "Smoke test Hermes desktop runtime")
    build_lines = active_lines(build_step)
    selector_lines = active_lines(selector_step)
    chatgpt_lines = active_lines(chatgpt_step)
    hermes_lines = active_lines(hermes_step)
    assert "id: build" in build_lines
    assert "id: image" in selector_lines
    assert "candidate-{1}-{2}" in build_step
    assert 'image="$(head -n 1 <<< "$IMAGE_TAGS")"' in selector_lines
    assert "image='${{ matrix.image }}@${{ steps.build.outputs.digest }}'" in selector_lines
    assert 'docker pull "$image"' in selector_lines
    for lines in (chatgpt_lines, hermes_lines):
        assert "IMAGE_UNDER_TEST: ${{ steps.image.outputs.image }}" in lines
        assert not any(":latest" in line for line in lines)
    assert 'docker buildx imagetools create "${tags[@]}" "$IMAGE_UNDER_TEST"' in promote_step
    assert "tests/smoke-chatgpt-desktop.sh" in chatgpt_step
    assert "tests/smoke-hermes-desktop.sh" in hermes_step
    assert "consumer-volume-sentinel" in desktop_smoke
    assert "x11-utils" in chatgpt_image
    assert "Smoke desktop with rootless Podman" in workflow
    assert "PELAGIAN_SHELL_CONFORMANCE_COMMIT:-7feb586b1b1dc3c706afbb16a336c14092ac7d5a" in desktop_smoke
    assert "--managed-count 2 --floating-count 1" in desktop_smoke
    assert "dialog-close" in desktop_smoke
    assert '"${GROTTO_CONFIG_BIND}:/config:Z"' in desktop_smoke
    assert "GROTTO_DESKTOP_PHASES" in desktop_smoke
    assert "podman info --format '{{.Host.Security.Rootless}}'" in bind_smoke
    assert "GROTTO_EXPECT_CONFIG_PERSISTENCE=true" in bind_smoke
    assert "ELECTRON_USE_SYSTEM_TITLE_BAR=1" not in chatgpt_image
    assert not re.search(r"(?m)^export ELECTRON_USE_SYSTEM_TITLE_BAR=", chatgpt_launcher)
    assert "--disable-features=CustomTitlebar,WaylandWindowDecorations" not in chatgpt_launcher
    assert "PELAGIAN_SHELL_WINDOW_CHROME" not in chatgpt_launcher
    assert "ELECTRON_USE_SYSTEM_TITLE_BAR" in chatgpt_policy
    assert "compatibility_exception_required" in chatgpt_policy
    assert "titleBarStyle:`hidden`" in chatgpt_policy
    assert "titleBarOverlay" in chatgpt_policy
    assert '"window_chrome"' in chatgpt_policy
    assert "/usr/local/bin/pelagian-shell-consumer" in desktop_docs
    assert "--enable-features=UseOzonePlatform" in desktop_docs
    assert "--ozone-platform=wayland" in desktop_docs
    assert "planner-only" not in desktop_docs
    assert "owns placement and automatic tiling" in desktop_docs
    assert "GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD" in desktop_docs
    assert "type=env,target=GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD" in desktop_docs

    with tempfile.TemporaryDirectory() as temporary_directory:
        session_dir = Path(temporary_directory) / "hermes-desktop"
        environment = os.environ | {
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/grotto-hermes-test-bus",
            "HERMES_DESKTOP_USER_DATA_DIR": str(session_dir),
        }
        environment.pop("GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD", None)
        result = subprocess.run(
            ["bash", str(DESKTOP_SESSION)],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2
        session_log = session_dir / "session.log"
        assert session_log.exists()
        assert "GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD is required" in session_log.read_text()

    # The pinned commit is repeated in the CI matrix and the in-image smoke;
    # a bump has to land in every copy or the build ships mismatched provenance.
    pinned_commit = "5fc308a70719a83cccdbba4c0e39c23f5a8239d5"
    assert pinned_commit in (ROOT / ".github/image-matrix.json").read_text()
    assert pinned_commit in DESKTOP_IMAGE_SMOKE.read_text()
    print("Hermes image contract tests passed")


if __name__ == "__main__":
    main()
