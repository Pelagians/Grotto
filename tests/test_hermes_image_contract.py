#!/usr/bin/env python3
"""Static contract checks for the Grotto Hermes image."""
import re
import os
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
    "91caa1525db1ecd98e94074e4008510311a41aa718abf7b41935e391fbde4619"
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
    desktop_smoke = DESKTOP_SMOKE.read_text()
    desktop_docs = DESKTOP_DOCS.read_text()
    workflow = WORKFLOW.read_text()
    chatgpt_image = (ROOT / "Containerfile.chatgpt-desktop").read_text()
    for containerfile in (desktop_image, chatgpt_image):
        assert re.findall(r"^ARG PELAGIAN_SHELL_IMAGE=(\S+)$", containerfile, re.M) == [
            SHELL_IMAGE
        ]
    assert "5fc308a70719a83cccdbba4c0e39c23f5a8239d5" in desktop_image
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
    assert "wlrctl toplevel list" in desktop_smoke
    assert "xlsclients -display :0 -l" in desktop_smoke
    assert "x11-utils" in desktop_image
    assert "--env XDG_RUNTIME_DIR=/config/.XDG" in desktop_smoke
    assert "--env WAYLAND_DISPLAY=wayland-1" in desktop_smoke
    assert "pgrep -f '[H]ermes'" in desktop_smoke
    assert "PELAGIAN_SHELL_SESSION_SENTINEL" not in desktop_smoke
    assert "ghcr.io/pelagians/grotto-hermes-desktop" in workflow
    build_step = workflow_step(workflow, "Build and publish desktop image")
    selector_step = workflow_step(workflow, "Select desktop image under test")
    chatgpt_step = workflow_step(workflow, "Smoke test ChatGPT desktop runtime")
    hermes_step = workflow_step(workflow, "Smoke test Hermes desktop runtime")
    build_lines = active_lines(build_step)
    selector_lines = active_lines(selector_step)
    chatgpt_lines = active_lines(chatgpt_step)
    hermes_lines = active_lines(hermes_step)
    assert "id: desktop-build" in build_lines
    assert "id: desktop-image" in selector_lines
    assert "if [[ '${{ github.event_name }}' == pull_request ]]; then" in selector_lines
    assert 'image="$(head -n 1 <<< "$IMAGE_TAGS")"' in selector_lines
    assert "image='${{ matrix.image }}@${{ steps.desktop-build.outputs.digest }}'" in selector_lines
    assert 'docker pull "$image"' in selector_lines
    for lines in (chatgpt_lines, hermes_lines):
        assert "IMAGE_UNDER_TEST: ${{ steps.desktop-image.outputs.image }}" in lines
        assert not any(":latest" in line for line in lines)
    assert '"$IMAGE_UNDER_TEST"' in chatgpt_lines
    assert (
        'CONTAINER_ENGINE=docker GROTTO_HERMES_DESKTOP_IMAGE="$IMAGE_UNDER_TEST" \\'
        in hermes_lines
    )
    assert "/usr/local/bin/pelagian-shell-consumer" in desktop_docs
    assert "--enable-features=UseOzonePlatform" in desktop_docs
    assert "--ozone-platform=wayland" in desktop_docs
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
    assert pinned_commit in workflow
    assert pinned_commit in DESKTOP_IMAGE_SMOKE.read_text()
    print("Hermes image contract tests passed")


if __name__ == "__main__":
    main()
