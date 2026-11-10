"""The operator probe observes governance gates without executing pending writes."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "runtimes/hermes/qualification_probe.py"
SPEC = importlib.util.spec_from_file_location("qualification_probe", SOURCE)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)

RECORD = "a" * 32
CALL = "b" * 32
GRANT = "c" * 32


class Refused(Exception):
    def __init__(self, status):
        self.status = status


class FakeClient:
    def __init__(self, *, stage, bindings=None):
        self.stage = stage
        self.bindings = bindings
        self.calls = []
        self.client = self

    async def aclose(self):
        pass

    async def request(self, method, suffix, *, body=None, key=None):
        self.calls.append((method, suffix))
        if suffix == "/tools":
            return {"bindings": self.bindings if self.bindings is not None else []}
        if method == "GET":
            return {"next_action": "complete" if self.stage == "replay" else self.stage}
        if self.stage in ("await_approval", "await_confirmation"):
            raise Refused(409)
        if self.stage == "revoked":
            raise Refused(403)
        return {"replayed": True, "next_action": "complete"}


def _run(monkeypatch, mode, *, bindings=None):
    client = FakeClient(stage=mode, bindings=bindings)
    monkeypatch.setattr(PROBE, "_bridge_module", lambda: SimpleNamespace(
        Nereus=lambda: client, BridgeError=Refused,
    ))
    result = asyncio.run(PROBE._check(SimpleNamespace(
        mode=mode, record_id=RECORD, call_id=CALL, grant_id=GRANT,
    )))
    return result, client.calls


@pytest.mark.parametrize("stage", ["await_approval", "await_confirmation"])
def test_pending_write_is_refused_before_execution(monkeypatch, stage):
    result, calls = _run(monkeypatch, stage)
    assert result["execution_refused"] is True
    assert calls == [
        ("GET", f"/calls/{CALL}"),
        ("POST", f"/calls/{CALL}/execute"),
        ("GET", f"/calls/{CALL}"),
    ]


def test_replay_returns_receipt_without_result(monkeypatch):
    result, calls = _run(monkeypatch, "replay")
    assert result == {"stage": "complete", "replayed": True, "result_absent": True}
    assert calls == [("GET", f"/calls/{CALL}"), ("POST", f"/calls/{CALL}/execute")]


def test_revoked_grant_disappears_and_later_call_is_refused(monkeypatch):
    result, calls = _run(monkeypatch, "revoked")
    assert result == {"stage": "revoked", "bindings": 0, "later_call_denied": True}
    assert calls == [("GET", "/tools"), ("POST", "/calls")]


def test_discovery_accepts_only_exact_grant_record_and_two_tools(monkeypatch):
    bindings = [{
        "package": "pelagian.synthetic", "grant_id": GRANT,
        "record_ids": [RECORD],
        "tools": [{"id": "read-item"}, {"id": "set-status"}],
    }]
    result, calls = _run(monkeypatch, "discovery", bindings=bindings)
    assert result == {"stage": "discovery", "bindings": 1, "tools": 2, "records": 1}
    assert calls == [("GET", "/tools")]
