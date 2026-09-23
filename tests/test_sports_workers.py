from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "runtimes" / "sports-workers"


def load(name: str, relative: str):
    sys.path.insert(0, str(COMMON))
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WorkerTests(unittest.TestCase):
    def test_market_fixture_emits_hashed_bundle(self) -> None:
        module = load(
            "market_probe", "runtimes/sports-market-probe/grotto_sports_market_probe.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "odds.json"
            fixture.write_text(
                json.dumps(
                    [
                        {
                            "id": "p1",
                            "bookmakers": [
                                {
                                    "key": "book",
                                    "markets": [
                                        {
                                            "key": "player_pass_yds",
                                            "outcomes": [
                                                {
                                                    "name": "Over",
                                                    "description": "P. Test",
                                                    "point": 250.5,
                                                    "price": 1.91,
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                )
            )
            job = root / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "job_id": "j1",
                        "event_id": "e1",
                        "provider": "fixture",
                        "provider_event_id": "p1",
                        "requested_market_keys": ["player_pass_yds"],
                        "fixture_path": str(fixture),
                        "max_requests": 1,
                    }
                )
            )
            output = root / "out.json"
            module.run(str(job), str(output))
            bundle = json.loads(output.read_text())
            self.assertEqual(bundle["quotes"][0]["player_name"], "P. Test")
            self.assertEqual(len(bundle["bundle_digest"]), 64)

    def test_source_failures_are_isolated(self) -> None:
        module = load(
            "source_probe", "runtimes/sports-source-probe/grotto_sports_source_probe.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "team.html"
            fixture.write_text("injury update")
            job = root / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "job_id": "j2",
                        "team_id": "DET",
                        "event_id": "e1",
                        "allowed_source_classes": ["team_official"],
                        "allowed_hosts": [],
                        "max_requests": 2,
                        "sources": [
                            {
                                "source_watch_id": "w1",
                                "source_class": "team_official",
                                "url": "https://example.invalid",
                                "fixture_path": str(fixture),
                            },
                            {
                                "source_watch_id": "w2",
                                "source_class": "public_beat",
                                "url": "https://example.invalid",
                            },
                        ],
                    }
                )
            )
            output = root / "out.json"
            module.run(str(job), str(output))
            bundle = json.loads(output.read_text())
            self.assertEqual(len(bundle["raw_artifacts"]), 1)
            self.assertEqual(
                bundle["failures"][0]["reason"], "SOURCE_CLASS_NOT_ALLOWED"
            )

    def test_playnow_worker_has_no_browser_actuation(self) -> None:
        path = ROOT / "runtimes/playnow-observer/grotto_playnow_observer.py"
        calls = {
            node.func.attr
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(
            calls & {"goto", "click", "fill", "press", "type", "close", "reload"}
        )

    def test_images_have_no_secret_values(self) -> None:
        for name in ("sports-market-probe", "sports-source-probe", "playnow-observer"):
            text = (ROOT / f"Containerfile.{name}").read_text()
            self.assertNotIn("API_KEY=", text)
            self.assertIn("USER 10001:10001", text)


if __name__ == "__main__":
    unittest.main()
