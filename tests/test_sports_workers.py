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
    def test_event_index_preserves_provider_identity_fields(self) -> None:
        module = load(
            "market_event_index", "runtimes/sports-market-probe/grotto_sports_market_probe.py"
        )
        rows = module._event_index(
            [
                {
                    "id": "provider-event",
                    "home_team": "Dallas Cowboys",
                    "away_team": "Baltimore Ravens",
                    "commence_time": "2026-09-27T20:25:00Z",
                }
            ]
        )
        self.assertEqual(rows[0]["provider_event_id"], "provider-event")
        self.assertEqual(rows[0]["home_team"], "Dallas Cowboys")
    def test_event_specific_market_discovery(self) -> None:
        module = load(
            "market_discovery", "runtimes/sports-market-probe/grotto_sports_market_probe.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "job_id": "discover-1",
                        "event_id": "event-1",
                        "provider": "fixture",
                        "provider_event_id": "provider-event-1",
                        "operation": "EVENT_DISCOVERY",
                        "fixture_path": str(ROOT / "tests/fixtures/sports-event-markets.json"),
                        "requested_market_keys": ["player_pass_yds", "team_totals", "totals_h1"],
                        "max_requests": 1,
                    }
                )
            )
            output = root / "out.json"
            module.run(str(job), str(output))
            bundle = json.loads(output.read_text())
            assert {item["market_key"] for item in bundle["market_availability"]} == {
                "player_pass_yds",
                "team_totals",
                "totals_h1",
            }
            assert bundle["request_stats"]["attempted"] == 1

    def test_prop_market_keys_requested_explicitly(self) -> None:
        module = load(
            "market_quotes", "runtimes/sports-market-probe/grotto_sports_market_probe.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "job_id": "quotes-1",
                        "event_id": "event-1",
                        "provider": "fixture",
                        "provider_event_id": "provider-event-1",
                        "operation": "EVENT_QUOTES",
                        "fixture_path": str(ROOT / "tests/fixtures/sports-event-odds.json"),
                        "requested_market_keys": ["player_pass_yds"],
                        "max_requests": 1,
                    }
                )
            )
            output = root / "out.json"
            module.run(str(job), str(output))
            bundle = json.loads(output.read_text())
            assert {item["market_key"] for item in bundle["quotes"]} == {"player_pass_yds"}

    def test_headline_only_response_does_not_count_as_prop_success(self) -> None:
        module = load(
            "headline_only", "runtimes/sports-market-probe/grotto_sports_market_probe.py"
        )
        availability, quotes, capabilities = module._quotes(
            {
                "job_id": "j",
                "event_id": "e",
                "provider": "fixture",
                "provider_event_id": "p",
                "requested_market_keys": ["player_pass_yds"],
            },
            {"id": "p", "bookmakers": [{"key": "book", "markets": [{"key": "h2h"}]}]},
            "2026-09-27T15:00:00Z",
            "raw-0",
        )
        assert availability == [] and quotes == []
        assert capabilities[0]["reason"] == "BOOK_UNSUPPORTED"
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

    def test_playnow_snapshot_contract_is_strict(self) -> None:
        module = load(
            "playnow_contract", "runtimes/playnow-observer/grotto_playnow_observer.py"
        )
        row = module._market(
            {
                "event_id": "event-1",
                "market_family": "TEAM_TOTAL",
                "market_key": "team_totals",
                "subject_id": "team-home",
                "selection": "Over",
                "period": "FULL_GAME",
                "line": 24.5,
                "price": 1.91,
                "status": "OBSERVED",
                "observed_at": "2026-09-23T20:00:00Z",
            }
        )
        self.assertEqual(row["raw_evidence_id"], "raw-0")

    def test_playnow_observed_price_cannot_be_missing(self) -> None:
        module = load(
            "playnow_missing_price", "runtimes/playnow-observer/grotto_playnow_observer.py"
        )
        with self.assertRaisesRegex(ValueError, "price is required"):
            module._market(
                {
                    "event_id": "event-1",
                    "market_family": "HEADLINE",
                    "market_key": "h2h",
                    "selection": "Home",
                    "period": "FULL_GAME",
                    "status": "OBSERVED",
                    "observed_at": "2026-09-23T20:00:00Z",
                }
            )

    def test_playnow_fixture_emits_caller_owned_bundle(self) -> None:
        module = load(
            "playnow_fixture", "runtimes/playnow-observer/grotto_playnow_observer.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.json"
            job.write_text(
                json.dumps(
                    {
                        "job_id": "playnow-1",
                        "event_id": "event-1",
                        "session_mode": "caller_owned",
                        "browser_session_id": "ephemeral-session-1",
                        "page_url": "https://www.playnow.com/sports",
                        "allowed_origins": ["https://www.playnow.com"],
                        "snapshot_path": str(
                            ROOT / "tests/fixtures/playnow-observation.json"
                        ),
                    }
                )
            )
            output = root / "bundle.json"
            module.run(str(job), str(output))
            bundle = json.loads(output.read_text())
            self.assertEqual(bundle["session_mode"], "caller_owned")
            self.assertEqual(bundle["markets"][0]["status"], "OBSERVED")
            self.assertEqual(
                bundle["sgp_observations"][0]["status"], "SGP_PRICE_NOT_OBSERVED"
            )

    def test_images_have_no_secret_values(self) -> None:
        for name in ("sports-market-probe", "sports-source-probe", "playnow-observer"):
            text = (ROOT / f"Containerfile.{name}").read_text()
            self.assertNotIn("API_KEY=", text)
            self.assertIn("USER 10001:10001", text)


if __name__ == "__main__":
    unittest.main()
