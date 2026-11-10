"""Load the rendered ConfigMap profile under staging's non-root read-only mode."""

from pathlib import Path
import os
import subprocess

import yaml

documents = list(yaml.safe_load_all(Path("/tmp/hermes-staging.yaml").read_text()))
config_map = next(item for item in documents if item.get("kind") == "ConfigMap")
profile = config_map["data"]["config.yaml"]
settings = yaml.safe_load(profile)
assert settings["model"] == {
    "default": "REPLACE_MODEL_ID",
    "provider": "custom:qualification",
}
assert settings["providers"]["qualification"]["key_env"] == "PELAGIAN_MODEL_API_KEY"
Path("/opt/data/config.yaml").write_text(profile, encoding="utf-8")
os.environ["PELAGIAN_MODEL_API_KEY"] = "synthetic-smoke-key"
from hermes_cli.runtime_provider import resolve_runtime_provider

runtime = resolve_runtime_provider(target_model="REPLACE_MODEL_ID")
assert runtime["base_url"] == "https://REPLACE_MODEL_PROVIDER_ORIGIN/v1"
assert runtime["api_key"] == "synthetic-smoke-key"
assert runtime["requested_provider"] == "custom:qualification"
result = subprocess.run(
    ["/opt/hermes/.venv/bin/hermes", "mcp", "list"],
    text=True, capture_output=True, check=True,
)
assert "pelagian_nereus" in result.stdout
assert "enabled" in result.stdout
print("Staging Hermes profile loaded under non-root read-only root filesystem")
