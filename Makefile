.PHONY: check check-container-engine image-openclaw image-chatgpt-desktop image-claude-desktop image-all

DETECTED_CONTAINER_ENGINE := $(shell if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then printf 'podman'; elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then printf 'sudo podman'; elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then printf 'docker'; fi)
CONTAINER_ENGINE ?= $(DETECTED_CONTAINER_ENGINE)
ifeq ($(strip $(CONTAINER_ENGINE)),)
CONTAINER_ENGINE := $(DETECTED_CONTAINER_ENGINE)
endif

GROTTO_OPENCLAW_IMAGE ?= grotto-openclaw:dev
GROTTO_CHATGPT_DESKTOP_IMAGE ?= grotto-chatgpt-desktop:dev
GROTTO_CLAUDE_DESKTOP_IMAGE ?= grotto-claude-desktop:dev
CODEX_DESKTOP_LINUX_REF ?= 7d4049b68b17bc663b8a934326fefcaca99e8ceb
CODEX_CLI_VERSION ?= latest
CODEX_DESKTOP_LINUX_SOURCE ?=
CLAUDE_DESKTOP_VERSION ?=

check:
	sh -n files/grotto-openclaw-entrypoint
	bash -n runtimes/chatgpt-desktop/root/defaults/autostart
	bash -n runtimes/chatgpt-desktop/root/defaults/autostart_wayland
	python3 -m py_compile runtimes/chatgpt-desktop/root/usr/local/bin/grotto-chatgpt-auth
	python3 -m py_compile runtimes/chatgpt-desktop/root/usr/local/bin/grotto-doctor
	python3 -m py_compile runtimes/chatgpt-desktop/verify-installed-policy.py
	bash -n runtimes/chatgpt-desktop/root/custom-cont-init.d/10-grotto-chatgpt-permissions
	bash -n runtimes/claude-desktop/root/defaults/autostart
	bash -n runtimes/claude-desktop/root/defaults/autostart_wayland
	bash -n runtimes/claude-desktop/root/custom-cont-init.d/10-grotto-claude-permissions
	python3 -m py_compile runtimes/claude-desktop/root/usr/local/bin/grotto-claude-browser
	python3 runtimes/claude-desktop/root/usr/local/bin/grotto-claude-browser --self-test
	grep -Fq 'target="_blank"' runtimes/claude-desktop/root/usr/share/grotto/claude-viewer-open.js
	grep -Fq 'parsed.protocol !== "https:"' runtimes/claude-desktop/root/usr/share/grotto/claude-viewer-open.js
	bash -n tests/claude-desktop-runtime.sh
	CODEX_DESKTOP_LINUX_SOURCE="$(CODEX_DESKTOP_LINUX_SOURCE)" python3 tests/test_codex_desktop_linux_patch.py
	python3 tests/test_grotto_doctor.py
	python3 tests/test_window_manager_config.py
	python3 tests/test_window_manager_config.py --installed-image
	python3 tests/test_verify_installed_chatgpt_policy.py

check-container-engine:
	@if [ -z "$(CONTAINER_ENGINE)" ]; then \
		echo "No usable container engine found. Tried rootless podman, sudo podman, and docker." >&2; \
		echo "Start a container daemon or rerun with CONTAINER_ENGINE='<engine command>'." >&2; \
		exit 2; \
	fi

image-openclaw: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile \
		-t $(GROTTO_OPENCLAW_IMAGE) \
		.

image-chatgpt-desktop: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile.chatgpt-desktop \
		--build-arg CODEX_DESKTOP_LINUX_REF="$(CODEX_DESKTOP_LINUX_REF)" \
		--build-arg CODEX_CLI_VERSION="$(CODEX_CLI_VERSION)" \
		-t $(GROTTO_CHATGPT_DESKTOP_IMAGE) \
		.

image-claude-desktop: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile.claude-desktop \
		--build-arg CLAUDE_DESKTOP_VERSION="$(CLAUDE_DESKTOP_VERSION)" \
		-t $(GROTTO_CLAUDE_DESKTOP_IMAGE) \
		.

image-all: image-openclaw image-chatgpt-desktop image-claude-desktop
