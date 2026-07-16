.PHONY: check check-container-engine image-openclaw image-chatgpt-desktop image-all

DETECTED_CONTAINER_ENGINE := $(shell if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then printf 'podman'; elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then printf 'sudo podman'; elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then printf 'docker'; fi)
CONTAINER_ENGINE ?= $(DETECTED_CONTAINER_ENGINE)
ifeq ($(strip $(CONTAINER_ENGINE)),)
CONTAINER_ENGINE := $(DETECTED_CONTAINER_ENGINE)
endif

GROTTO_OPENCLAW_IMAGE ?= grotto-openclaw:dev
GROTTO_CHATGPT_DESKTOP_IMAGE ?= grotto-chatgpt-desktop:dev
CODEX_DESKTOP_LINUX_REF ?= 52e9701e3f1be291821cff904b6cd4bdce30998d
CODEX_CLI_VERSION ?= latest

check:
	sh -n files/grotto-openclaw-entrypoint
	bash -n runtimes/chatgpt-desktop/root/defaults/autostart
	bash -n runtimes/chatgpt-desktop/root/usr/local/bin/grotto-chatgpt-auth
	bash -n runtimes/chatgpt-desktop/root/custom-cont-init.d/10-grotto-chatgpt-permissions

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

image-all: image-openclaw image-chatgpt-desktop
