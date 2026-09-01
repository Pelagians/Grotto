#!/usr/bin/env python3
"""Static contract checks for the Grotto Hermes image."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINERFILE = ROOT / "Containerfile.hermes"
HOOK = ROOT / "files/grotto-agent-entrypoint"
SMOKE = ROOT / "tests/smoke-hermes.sh"
DESKTOP_CONTAINERFILE = ROOT / "Containerfile.hermes-desktop"
DESKTOP_AUTOSTART = ROOT / "runtimes/hermes-desktop/root/defaults/autostart_wayland"
DESKTOP_INIT = ROOT / "runtimes/hermes-desktop/root/custom-cont-init.d/30-grotto-hermes-desktop"
DESKTOP_SESSION = ROOT / "runtimes/hermes-desktop/root/usr/local/bin/grotto-hermes-desktop-session"
DESKTOP_SMOKE = ROOT / "tests/smoke-hermes-desktop.sh"
DESKTOP_IMAGE_SMOKE = ROOT / "tests/hermes-desktop-image-smoke.sh"
WORKFLOW = ROOT / ".github/workflows/build.yml"


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
    desktop_autostart = DESKTOP_AUTOSTART.read_text()
    desktop_init = DESKTOP_INIT.read_text()
    desktop_session = DESKTOP_SESSION.read_text()
    desktop_smoke = DESKTOP_SMOKE.read_text()
    workflow = WORKFLOW.read_text()
    assert "ghcr.io/pelagians/pelagian-shell@sha256:c444a61ba818bf7d0cad8d32574732e8da16099e018b760d2fc05d90bfb3f490" in desktop_image
    assert "5fc308a70719a83cccdbba4c0e39c23f5a8239d5" in desktop_image
    assert "node:22-bookworm@sha256:8a34c4ab3ea2c5cd194f07e317b2a8f09461d3c8b05c4e34c8ccd56d56024c4d" in desktop_image
    assert "npm run builder -- --linux deb --publish never" in desktop_image
    assert "pipefail" not in desktop_autostart
    assert "sh -n runtimes/hermes-desktop/root/defaults/autostart_wayland" in (ROOT / "Makefile").read_text()
    assert "HERMES_DESKTOP_USER_DATA_DIR=/config/hermes-desktop" in desktop_image
    assert "HERMES_DESKTOP_PASSWORD_STORE=gnome-libsecret" in desktop_image
    assert 'VOLUME ["/config", "/workspace", "/tools", "/home/linuxbrew/.linuxbrew", "/cache"]' in desktop_image
    assert "/opt/data" not in desktop_image
    assert "secure-token-storage.json" in desktop_init
    assert '"on":true' in desktop_init
    assert "GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD" in desktop_session
    assert "gnome-keyring-daemon --unlock" in desktop_session
    assert "dbus-launch --sh-syntax" in desktop_session
    assert "dbus-run-session" not in desktop_session
    assert "/config/hermes-desktop/session.log" in desktop_session
    assert "/config/hermes-desktop/session.log" in desktop_smoke
    assert "wlrctl toplevel list" in desktop_smoke
    assert "ghcr.io/pelagians/grotto-hermes-desktop" in workflow

    # The pinned commit is repeated in the CI matrix and the in-image smoke;
    # a bump has to land in every copy or the build ships mismatched provenance.
    pinned_commit = "5fc308a70719a83cccdbba4c0e39c23f5a8239d5"
    assert pinned_commit in workflow
    assert pinned_commit in DESKTOP_IMAGE_SMOKE.read_text()
    print("Hermes image contract tests passed")


if __name__ == "__main__":
    main()
