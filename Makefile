
.PHONY: test test-browser-runtime validate-schemas validate-manifests run-workerd image-documents smoke-documents-container

DETECTED_CONTAINER_ENGINE := $(shell if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then printf 'podman'; elif command -v sudo >/dev/null 2>&1 && sudo -n podman info >/dev/null 2>&1; then printf 'sudo podman'; elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then printf 'docker'; fi)
CONTAINER_ENGINE ?= $(DETECTED_CONTAINER_ENGINE)
ifeq ($(strip $(CONTAINER_ENGINE)),)
CONTAINER_ENGINE := $(DETECTED_CONTAINER_ENGINE)
endif
OPENQUAD_DOCUMENTS_IMAGE ?= openquad-documents:smoke

.PHONY: check-container-engine
check-container-engine:
	@if [ -z "$(CONTAINER_ENGINE)" ]; then \
		echo "No usable container engine found. Tried rootless podman, sudo podman, and docker." >&2; \
		echo "Start a container daemon or rerun with CONTAINER_ENGINE='<engine command>'." >&2; \
		exit 2; \
	fi

validate-schemas:
	uv run --project workerd --with jsonschema python scripts/validate_openquad_contracts.py .

validate-manifests: validate-schemas

test: test-browser-runtime
	PYTHONPATH=. uv run --project workerd --with pytest --with httpx --with fastapi --with jsonschema python -m pytest workerd/tests -q

test-browser-runtime:
	node --test tests/browser-runtime/*.test.mjs

run-workerd:
	PYTHONPATH=. uv run --project workerd openquad-workerd

image-documents: check-container-engine
	$(CONTAINER_ENGINE) build \
		-f Containerfile \
		--build-arg OPENQUAD_TEMPLATE=documents \
		--build-arg OPENQUAD_IMAGE_NAME=openquad-documents \
		--build-arg "OPENQUAD_VERIFY_TOOLS=pdfinfo pdftotext qpdf tesseract ocrmypdf" \
		-t $(OPENQUAD_DOCUMENTS_IMAGE) \
		.

smoke-documents-container:
	CONTAINER_ENGINE="$(CONTAINER_ENGINE)" \
	OPENQUAD_DOCUMENTS_IMAGE="$(OPENQUAD_DOCUMENTS_IMAGE)" \
	scripts/smoke_documents_container.sh
