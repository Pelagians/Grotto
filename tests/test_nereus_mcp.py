"""Behavior checks for the synthetic Nereus MCP bridge."""
import asyncio
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import anyio
import httpx2 as httpx
from mcp import ClientSession
from mcp.server import NotificationOptions, Server

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nereus_mcp", ROOT / "runtimes/hermes/nereus_mcp.py"
)
bridge_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge_module)


def binding(grant="a" * 32, record="b" * 32, effect="read"):
    tool = {
        "id": "read-item" if effect == "read" else "set-status",
        "description": "Synthetic tool",
        "inputSchema": {"type": "object", "properties": {"record_id": {"type": "string"}}},
        "outputSchema": {"type": "object"},
        "effect": effect,
        "actionType": "synthetic." + effect,
        "record_ids": [record],
    }
    return {
        "package": "pelagian.synthetic", "release": "0.1.0",
        "grant_id": grant, "record_ids": [record], "tools": [tool],
    }


class FakeNereus:
    def __init__(self, bindings, *, next_action="execute"):
        self.bindings = bindings
        self.next_action = next_action
        self.requests = []

    async def request(self, method, suffix, *, body=None, key=None):
        self.requests.append((method, suffix, body, key))
        if suffix == "/tools":
            return {"bindings": self.bindings}
        if suffix == "/calls":
            return {"call_id": "c" * 32, "next_action": self.next_action}
        if suffix.endswith("/execute"):
            return {"call_id": "c" * 32, "next_action": "complete", "result": {"status": "done"}}
        return {"call_id": "c" * 32, "next_action": "await_confirmation"}


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_discovery_and_revocation(self):
        fake = FakeNereus([binding()])
        bridge = bridge_module.Bridge(fake)
        names = [tool.name for tool in (await bridge.list_tools()).tools]
        self.assertIn("pelagian_synthetic_read_item", names)
        fake.bindings = []
        names = [tool.name for tool in (await bridge.list_tools()).tools]
        self.assertNotIn("pelagian_synthetic_read_item", names)

    async def test_read_and_pending_write(self):
        fake = FakeNereus([binding()])
        bridge = bridge_module.Bridge(fake)
        args = {"record_id": "b" * 32}
        result = await bridge.call_tool(None, SimpleNamespace(
            name="pelagian_synthetic_read_item", arguments=args,
        ))
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["next_action"], "complete")
        self.assertEqual(fake.requests[1][2]["grant_id"], "a" * 32)
        self.assertTrue(fake.requests[1][3])
        fake.bindings = [binding(effect="write")]
        fake.next_action = "await_approval"
        pending = await bridge.call_tool(None, SimpleNamespace(
            name="pelagian_synthetic_set_status", arguments=args,
        ))
        self.assertEqual(pending.structured_content["next_action"], "await_approval")
        self.assertEqual(sum(path.endswith("/execute") for _, path, _, _ in fake.requests), 1)

    async def test_equivalent_overlapping_grants_choose_one_without_scope_expansion(self):
        fake = FakeNereus([binding("d" * 32), binding("a" * 32)])
        bridge = bridge_module.Bridge(fake)
        await bridge.call_tool(None, SimpleNamespace(
            name="pelagian_synthetic_read_item", arguments={"record_id": "b" * 32},
        ))
        self.assertEqual(fake.requests[1][2]["grant_id"], "a" * 32)
        denied = await bridge.call_tool(None, SimpleNamespace(
            name="pelagian_synthetic_read_item", arguments={"record_id": "e" * 32},
        ))
        self.assertTrue(denied.is_error)

    async def test_conflicting_contract_fails_discovery(self):
        first = binding()
        second = binding("d" * 32)
        second["release"] = "0.2.0"
        with self.assertRaises(bridge_module.BridgeError):
            await bridge_module.Bridge(FakeNereus([first, second])).list_tools()

    async def test_normalized_names_and_invalid_origins_fail_closed(self):
        first = binding()
        second = binding("d" * 32)
        second["package"] = "pelagian_synthetic"
        with self.assertRaises(bridge_module.BridgeError):
            await bridge_module.Bridge(FakeNereus([first, second])).list_tools()
        for unsafe in (
            "http://nereus.example.test",
            "https://user:secret@nereus.example.test",
            "https://nereus.example.test/tenant",
        ):
            with self.assertRaises(ValueError):
                bridge_module.Nereus({
                    "PELAGIAN_TENANT_ID": "tenant-one",
                    "PELAGIAN_NEREUS_URL": unsafe,
                    "PELAGIAN_LOCAL_TOKEN_FILE": "/tmp/agent-token",
                })

    async def test_revocation_notifies_hermes_tool_registry(self):
        fake = FakeNereus([binding()])
        bridge = bridge_module.Bridge(fake)
        changed = asyncio.Event()

        async def notify():
            changed.set()

        real_sleep = asyncio.sleep

        async def quick_sleep(_seconds):
            await real_sleep(0)

        with patch.object(bridge_module.asyncio, "sleep", new=quick_sleep):
            await bridge.list_tools(SimpleNamespace(
                session=SimpleNamespace(send_tool_list_changed=notify),
            ))
            fake.bindings = []
            await asyncio.wait_for(changed.wait(), 1)
            bridge._watch_task.cancel()
            await asyncio.gather(bridge._watch_task, return_exceptions=True)
        self.assertTrue(changed.is_set())

    async def test_native_mcp_protocol_roundtrip(self):
        fake = FakeNereus([binding()])
        bridge = bridge_module.Bridge(fake)
        server = Server(
            "pelagian-nereus-test", version="0.1.0",
            on_list_tools=bridge.list_tools, on_call_tool=bridge.call_tool,
        )
        to_server_send, to_server_recv = anyio.create_memory_object_stream(10)
        to_client_send, to_client_recv = anyio.create_memory_object_stream(10)
        options = server.create_initialization_options(
            NotificationOptions(tools_changed=True)
        )
        self.assertTrue(options.capabilities.tools.list_changed)
        async with anyio.create_task_group() as group:
            group.start_soon(
                server.run, to_server_recv, to_client_send, options,
            )
            async with ClientSession(to_client_recv, to_server_send) as client:
                await client.initialize()
                listed = await client.list_tools()
                self.assertIn(
                    "pelagian_synthetic_read_item",
                    [tool.name for tool in listed.tools],
                )
                result = await client.call_tool(
                    "pelagian_synthetic_read_item",
                    {"record_id": "b" * 32},
                )
                self.assertEqual(result.structured_content["next_action"], "complete")
            group.cancel_scope.cancel()

    async def test_action_helpers_reject_path_injection(self):
        fake = FakeNereus([])
        bridge = bridge_module.Bridge(fake)
        for name, arguments in (
            ("pelagian_action_status", {"call_id": "../connections"}),
            ("pelagian_resume_action", {
                "call_id": "x" * 32 + "/execute",
                "arguments": {"record_id": "b" * 32},
            }),
        ):
            result = await bridge.call_tool(None, SimpleNamespace(
                name=name, arguments=arguments,
            ))
            self.assertTrue(result.is_error)
        self.assertEqual(fake.requests, [])

    async def test_local_token_is_reread_and_oauth_refreshes(self):
        with tempfile.TemporaryDirectory() as root:
            token_path = Path(root) / "token"
            token_path.write_text("first")
            local = bridge_module.Nereus({
                "PELAGIAN_TENANT_ID": "tenant-one",
                "PELAGIAN_NEREUS_URL": "http://127.0.0.1:8000",
                "PELAGIAN_LOCAL_TOKEN_FILE": str(token_path),
            })
            self.assertEqual(await local.token(), "first")
            token_path.write_text("second")
            self.assertEqual(await local.token(), "second")
            secret_path = Path(root) / "secret"
            secret_path.write_text("private")
            seen = []
            def handler(request):
                seen.append(request.content)
                return httpx.Response(200, json={
                    "access_token": "short-token", "expires_in": 120,
                })
            oauth = bridge_module.Nereus({
                "PELAGIAN_TENANT_ID": "tenant-one",
                "PELAGIAN_NEREUS_URL": "https://nereus.example.test",
                "PELAGIAN_OAUTH_TOKEN_URL": "https://id.example.test/token",
                "PELAGIAN_OAUTH_CLIENT_ID": "hermes",
                "PELAGIAN_OAUTH_CLIENT_SECRET_FILE": str(secret_path),
            }, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            self.assertEqual(await oauth.token(), "short-token")
            self.assertEqual(await oauth.token(), "short-token")
            self.assertEqual(len(seen), 1)
            oauth._expires = 0
            self.assertEqual(await oauth.token(), "short-token")
            self.assertEqual(len(seen), 2)
            await oauth.client.aclose()
            await local.client.aclose()


if __name__ == "__main__":
    unittest.main()
