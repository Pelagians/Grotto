"""Operator-only synthetic staging checks using the bridge's own OAuth client."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import socket
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _bridge_module():
    path = Path(__file__).with_name("pelagian-nereus-mcp.py")
    spec = importlib.util.spec_from_file_location("pelagian_nereus_mcp", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Nereus bridge is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _check(args) -> dict:
    bridge = _bridge_module()
    client = bridge.Nereus()
    try:
        arguments = {"record_id": args.record_id, "status": "done"}
        if args.mode == "discovery":
            discovery = await client.request("GET", "/tools")
            bindings = discovery.get("bindings", [])
            if len(bindings) != 1:
                raise RuntimeError("agent discovery is not limited to one grant")
            binding = bindings[0]
            if (
                binding.get("package") != "pelagian.synthetic"
                or binding.get("grant_id") != args.grant_id
                or binding.get("record_ids") != [args.record_id]
                or {tool.get("id") for tool in binding.get("tools", [])}
                != {"read-item", "set-status"}
            ):
                raise RuntimeError("agent discovery exceeds the synthetic delegation")
            return {"stage": "discovery", "bindings": 1, "tools": 2, "records": 1}
        if args.mode in ("await_approval", "await_confirmation"):
            before = await client.request("GET", f"/calls/{args.call_id}")
            if before.get("next_action") != args.mode:
                raise RuntimeError("action is not at the expected pending stage")
            try:
                await client.request(
                    "POST", f"/calls/{args.call_id}/execute",
                    body={"arguments": arguments},
                )
            except bridge.BridgeError as exc:
                if exc.status != 409:
                    raise RuntimeError("unexpected pre-execution refusal") from None
            else:
                raise RuntimeError("write executed before approval and confirmation")
            after = await client.request("GET", f"/calls/{args.call_id}")
            if after.get("next_action") != args.mode:
                raise RuntimeError("pending action changed after refused execution")
            return {"stage": args.mode, "execution_refused": True}

        if args.mode == "replay":
            before = await client.request("GET", f"/calls/{args.call_id}")
            if before.get("next_action") != "complete":
                raise RuntimeError("write is not complete")
            replay = await client.request(
                "POST", f"/calls/{args.call_id}/execute",
                body={"arguments": arguments},
            )
            if replay.get("replayed") is not True or "result" in replay:
                raise RuntimeError("completed retry repeated or replayed content")
            return {"stage": "complete", "replayed": True, "result_absent": True}

        discovery = await client.request("GET", "/tools")
        if discovery.get("bindings") != []:
            raise RuntimeError("revoked grant remains discoverable")
        try:
            await client.request(
                "POST", "/calls",
                body={
                    "grant_id": args.grant_id,
                    "tool_id": "read-item",
                    "arguments": {"record_id": args.record_id},
                },
                key=uuid4().hex,
            )
        except bridge.BridgeError as exc:
            if exc.status != 403:
                raise RuntimeError("unexpected post-revocation response") from None
        else:
            raise RuntimeError("revoked grant accepted a later call")
        return {"stage": "revoked", "bindings": 0, "later_call_denied": True}
    finally:
        await client.client.aclose()


def _usage() -> dict:
    state = Path("/opt/data/state.db")
    if not state.is_file():
        raise RuntimeError("Hermes session database is missing")
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        sessions = connection.execute(
            "SELECT id, model, billing_provider, estimated_cost_usd, "
            "input_tokens, output_tokens, api_call_count FROM sessions"
        ).fetchall()
        if len(sessions) != 1:
            raise RuntimeError("expected one isolated Hermes session")
        session_id, model, provider, cost, inputs, outputs, calls = sessions[0]
        turns = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
            (session_id,),
        ).fetchone()[0]
        if turns != 2 or not calls:
            raise RuntimeError("expected two user turns and a model call")
    return {
        "session_id": session_id,
        "model": model,
        "provider": provider,
        "estimated_cost_usd": cost,
        "input_tokens": inputs,
        "output_tokens": outputs,
        "api_calls": calls,
        "user_turns": turns,
    }


def _network() -> dict:
    # DNS must work; a failed lookup is not evidence that egress is restricted.
    addresses = socket.getaddrinfo(
        "example.com", 443, family=socket.AF_INET, type=socket.SOCK_STREAM,
    )
    if not addresses:
        raise RuntimeError("external DNS lookup failed")
    address = addresses[0][4]
    try:
        with socket.create_connection(address, timeout=3):
            pass
    except OSError:
        return {"stage": "network", "unapproved_tcp_443_blocked": True}
    raise RuntimeError("unapproved external TCP egress is reachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(
        "discovery", "await_approval", "await_confirmation", "replay", "revoked",
        "usage", "network",
    ))
    parser.add_argument("--record-id")
    parser.add_argument("--call-id")
    parser.add_argument("--grant-id")
    args = parser.parse_args(argv)
    if args.mode not in ("usage", "network") and (
        not args.record_id or not re.fullmatch(r"[0-9a-f]{32}", args.record_id)
    ):
        parser.error("record ID must be a 32-character lowercase hex reference")
    if args.mode in ("discovery", "revoked"):
        if not args.grant_id or not re.fullmatch(r"[0-9a-f]{32}", args.grant_id):
            parser.error("discovery/revocation checks require a grant ID")
    elif args.mode not in ("usage", "network") and (
        not args.call_id or not re.fullmatch(r"[0-9a-f]{32}", args.call_id)
    ):
        parser.error("pending/replay checks require a call ID")
    try:
        result = (
            _usage() if args.mode == "usage" else
            _network() if args.mode == "network" else
            asyncio.run(_check(args))
        )
    except Exception:
        print("synthetic qualification probe failed", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
