
.PHONY: test validate-schemas validate-manifests run-workerd

validate-schemas:
	uv run --project workerd --with jsonschema python scripts/validate_openquad_contracts.py .

validate-manifests: validate-schemas

test:
	PYTHONPATH=. uv run --project workerd --with pytest --with httpx --with fastapi --with jsonschema python -m pytest workerd/tests -q

run-workerd:
	PYTHONPATH=. uv run --project workerd openquad-workerd
