
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMAS = {
    "manifest": "schemas/openquad-worker-manifest.schema.json",
    "task": "schemas/openquad-task.schema.json",
    "result": "schemas/openquad-task-result.schema.json",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validator(root: Path, rel_path: str) -> Draft202012Validator:
    schema = _load_json(root / rel_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate(validator: Draft202012Validator, payload: dict[str, Any], path: Path) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        rendered = "; ".join(f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors)
        raise ValueError(f"{path}: {rendered}")


def validate_repo(root: Path) -> dict[str, int]:
    root = Path(root)
    schema_files = sorted((root / "schemas").glob("*.schema.json"))
    for schema_file in schema_files:
        Draft202012Validator.check_schema(_load_json(schema_file))

    manifest_validator = _validator(root, SCHEMAS["manifest"])
    task_validator = _validator(root, SCHEMAS["task"])
    result_validator = _validator(root, SCHEMAS["result"])

    manifest_paths = sorted((root / "templates").glob("*/openquad.manifest.json"))
    for path in manifest_paths:
        manifest = _load_json(path)
        _validate(manifest_validator, manifest, path)
        supported = set(manifest.get("supported_task_types", []))
        for capability in manifest.get("capabilities", []):
            for task_type in capability.get("task_types", []):
                if task_type not in supported:
                    raise ValueError(f"{path}: capability task_type {task_type} missing from supported_task_types")

    example_count = 0
    for path in sorted((root / "templates").glob("*/examples/*.json")):
        payload = _load_json(path)
        if path.name.endswith(".task.json"):
            _validate(task_validator, payload, path)
            example_count += 1
        elif path.name.endswith(".result.json"):
            _validate(result_validator, payload, path)
            example_count += 1

    return {"schemas": len(schema_files), "manifests": len(manifest_paths), "examples": example_count}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    result = validate_repo(root)
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
