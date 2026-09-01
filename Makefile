.PHONY: check check-container-engine image-openclaw image-chatgpt-desktop image-openadapt-teach image-hermes image-hermes-desktop image-all smoke-hermes smoke-hermes-desktop

DETECTED_CONTAINER_ENGINE := $(shell if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then printf 'podman'; elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then printf 'sudo podman'; elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then printf 'docker'; fi)
CONTAINER_ENGINE ?= $(DETECTED_CONTAINER_ENGINE)
ifeq ($(strip $(CONTAINER_ENGINE)),)
CONTAINER_ENGINE := $(DETECTED_CONTAINER_ENGINE)
endif

GROTTO_OPENCLAW_IMAGE ?= grotto-openclaw:dev
GROTTO_CHATGPT_DESKTOP_IMAGE ?= grotto-chatgpt-desktop:dev
GROTTO_HERMES_IMAGE ?= grotto-hermes:dev
GROTTO_HERMES_DESKTOP_IMAGE ?= grotto-hermes-desktop:dev
GROTTO_OPENADAPT_TEACH_IMAGE ?= grotto-openadapt-teach:dev
CHATGPT_PACKAGE_VERSION ?= 26.820.60940

check:
	python3 tests/test_hermes_image_contract.py
	sh -n files/grotto-openclaw-entrypoint
	bash -n runtimes/chatgpt-desktop/root/defaults/autostart
	bash -n runtimes/chatgpt-desktop/root/defaults/autostart_wayland
	python3 -m py_compile runtimes/chatgpt-desktop/root/usr/local/bin/grotto-chatgpt-auth
	python3 -m py_compile runtimes/chatgpt-desktop/root/usr/local/bin/grotto-doctor
	python3 -m py_compile runtimes/chatgpt-desktop/verify-installed-policy.py
	bash -n runtimes/chatgpt-desktop/root/custom-cont-init.d/10-grotto-chatgpt-permissions
	sh -n runtimes/hermes-desktop/root/defaults/autostart_wayland
	bash -n runtimes/hermes-desktop/root/custom-cont-init.d/30-grotto-hermes-desktop
	bash -n runtimes/hermes-desktop/root/usr/local/bin/grotto-hermes-desktop-session
	bash -n tests/hermes-desktop-image-smoke.sh
	bash -n tests/smoke-hermes-desktop.sh
	python3 tests/test_grotto_doctor.py
	python3 tests/test_window_manager_config.py
	python3 tests/test_window_manager_config.py --installed-image
	python3 tests/test_verify_installed_chatgpt_policy.py
	python3 tests/test_openadapt_teach_adapter.py
	python3 tests/test_openadapt_teach_policy.py
	python3 tests/test_openadapt_compat_canary.py

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
		--build-arg CHATGPT_PACKAGE_VERSION="$(CHATGPT_PACKAGE_VERSION)" \
		-t $(GROTTO_CHATGPT_DESKTOP_IMAGE) \
		.

image-openadapt-teach: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile.openadapt-teach \
		-t $(GROTTO_OPENADAPT_TEACH_IMAGE) \
		.

image-hermes: check-container-engine
	$(CONTAINER_ENGINE) build -f Containerfile.hermes -t $(GROTTO_HERMES_IMAGE) .

image-hermes-desktop: check-container-engine
	$(CONTAINER_ENGINE) build -f Containerfile.hermes-desktop -t $(GROTTO_HERMES_DESKTOP_IMAGE) .

smoke-hermes: check-container-engine
	CONTAINER_ENGINE="$(CONTAINER_ENGINE)" GROTTO_HERMES_IMAGE="$(GROTTO_HERMES_IMAGE)" tests/smoke-hermes.sh

smoke-hermes-desktop: check-container-engine
	CONTAINER_ENGINE="$(CONTAINER_ENGINE)" GROTTO_HERMES_DESKTOP_IMAGE="$(GROTTO_HERMES_DESKTOP_IMAGE)" tests/smoke-hermes-desktop.sh

image-all: image-openclaw image-chatgpt-desktop image-openadapt-teach image-hermes image-hermes-desktop
