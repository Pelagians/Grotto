
.PHONY: test test-browser-runtime validate-schemas validate-manifests run-workerd image-documents smoke-documents-container

DETECTED_CONTAINER_ENGINE := $(shell if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then printf 'podman'; elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then printf 'sudo podman'; elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then printf 'docker'; fi)
CONTAINER_ENGINE ?= $(DETECTED_CONTAINER_ENGINE)
ifeq ($(strip $(CONTAINER_ENGINE)),)
CONTAINER_ENGINE := $(DETECTED_CONTAINER_ENGINE)
endif
GROTTO_DOCUMENTS_IMAGE ?= grotto-documents:smoke

.PHONY: check-container-engine
check-container-engine:
	@if [ -z "$(CONTAINER_ENGINE)" ]; then \
		echo "No usable container engine found. Tried rootless podman, sudo podman, and docker." >&2; \
		echo "Start a container daemon or rerun with CONTAINER_ENGINE='<engine command>'." >&2; \
		exit 2; \
	fi

validate-schemas:
	uv run --project workerd --with jsonschema python scripts/validate_grotto_contracts.py .

validate-manifests: validate-schemas

test:
	PYTHONPATH=. uv run --project workerd --with pytest --with httpx --with fastapi --with jsonschema python -m pytest workerd/tests -q

run-workerd:
	PYTHONPATH=. uv run --project workerd grotto-workerd

image-documents: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile \
		--build-arg GROTTO_TEMPLATE=documents \
		--build-arg GROTTO_IMAGE_NAME=grotto-documents \
		--build-arg "GROTTO_VERIFY_TOOLS=pdfinfo pdftotext qpdf tesseract ocrmypdf" \
		-t $(GROTTO_DOCUMENTS_IMAGE) \
		.

smoke-documents-container:
	CONTAINER_ENGINE="$(CONTAINER_ENGINE)" \
	GROTTO_DOCUMENTS_IMAGE="$(GROTTO_DOCUMENTS_IMAGE)" \
	scripts/smoke_documents_container.sh
