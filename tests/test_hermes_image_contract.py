#!/usr/bin/env python3
"""Static contract checks for the Grotto Hermes image."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINERFILE = ROOT / "Containerfile.hermes"
HOOK = ROOT / "files/grotto-agent-entrypoint"
SMOKE = ROOT / "tests/smoke-hermes.sh"


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
    assert "chown -R hermes:hermes" not in smoke
    assert "brew install hello" in smoke
    assert "run_name-recreated" in smoke
    print("Hermes image contract tests passed")


if __name__ == "__main__":
    main()
