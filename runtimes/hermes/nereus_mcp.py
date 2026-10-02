"""Stdio MCP bridge to Nereus's delegated app API (synthetic staging only)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2 as httpx
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool


class BridgeError(Exception):
    def __init__(self, status: int | None = None):
        self.status = status
        super().__init__("Nereus app request failed")


def _origin(value: str, *, local_http: bool = False) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.path not in ("", "/") or (
        parsed.query or parsed.fragment
    ):
        raise ValueError("Nereus origin must not contain credentials or a path")
    if parsed.scheme == "https" and parsed.hostname:
        return value.rstrip("/")
    if local_http and parsed.scheme == "http" and parsed.hostname in (
        "localhost", "127.0.0.1",
    ):
        return value.rstrip("/")
    raise ValueError("Nereus origin must be HTTPS, or loopback HTTP for local tests")


def _name(package: str, tool_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", package + "__" + tool_id).strip("_")


def _call_id(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise BridgeError()
    return value


class Nereus:
    def __init__(self, env=None, client=None):
        env = env or os.environ
        self.tenant = env["PELAGIAN_TENANT_ID"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.tenant):
            raise ValueError("Invalid tenant identifier")
        self.base = _origin(
            env["PELAGIAN_NEREUS_URL"],
            local_http=bool(env.get("PELAGIAN_LOCAL_TOKEN_FILE")),
        )
        self.local_file = env.get("PELAGIAN_LOCAL_TOKEN_FILE")
        self.oauth_url = env.get("PELAGIAN_OAUTH_TOKEN_URL")
        self.client_id = env.get("PELAGIAN_OAUTH_CLIENT_ID")
        self.secret_file = env.get("PELAGIAN_OAUTH_CLIENT_SECRET_FILE")
        self.audience = env.get("PELAGIAN_OAUTH_AUDIENCE")
        if bool(self.local_file) == bool(self.oauth_url):
            raise ValueError("Configure exactly one agent authentication mode")
        if self.oauth_url and (not self.client_id or not self.secret_file):
            raise ValueError("OAuth client credentials are incomplete")
        if self.oauth_url:
            token_url = urlsplit(self.oauth_url)
            if token_url.scheme != "https" or not token_url.hostname or (
                token_url.username or token_url.password or token_url.fragment
            ):
                raise ValueError("OAuth token URL must be HTTPS")
        self.client = client or httpx.AsyncClient(
            timeout=20.0, follow_redirects=False, trust_env=False
        )
        self._token = ""
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        if self.local_file:
            value = Path(self.local_file).read_text().strip()
            if not value:
                raise BridgeError()
            return value
        async with self._lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": Path(self.secret_file).read_text().strip(),
            }
            if self.audience:
                data["audience"] = self.audience
            try:
                response = await self.client.post(self.oauth_url, data=data)
                if response.status_code != 200:
                    raise BridgeError(response.status_code)
                payload = response.json()
                token = payload["access_token"]
                ttl = int(payload["expires_in"])
                if not isinstance(token, str) or not token or ttl < 60:
                    raise BridgeError()
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise BridgeError() from exc
            self._token = token
            self._expires = time.monotonic() + max(1, ttl - 30)
            return token

    async def request(self, method: str, suffix: str, *, body=None, key=None):
        path = f"/api/v1/tenants/{self.tenant}/agent-apps{suffix}"
        headers = {
            "Authorization": "Bearer " + await self.token(),
            "Cache-Control": "no-store",
        }
        if key:
            headers["Idempotency-Key"] = key
        try:
            response = await self.client.request(
                method, self.base + path, headers=headers, json=body
            )
            if response.status_code >= 400:
                raise BridgeError(response.status_code)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BridgeError() from exc


def _bindings(payload):
    names = {}
    for binding in payload["bindings"]:
        for tool in binding["tools"]:
            name = _name(binding["package"], tool["id"])
            candidate = (binding, tool)
            existing = names.get(name)
            if existing and (
                existing[0][0]["package"] != binding["package"]
                or existing[0][0]["release"] != binding["release"]
                or existing[0][1]["id"] != tool["id"]
                or existing[0][1]["inputSchema"] != tool["inputSchema"]
                or existing[0][1]["effect"] != tool["effect"]
                or existing[0][1]["actionType"] != tool["actionType"]
                or existing[0][1]["outputSchema"] != tool["outputSchema"]
            ):
                raise BridgeError()
            names.setdefault(name, []).append(candidate)
    return names


def _result(value, *, error=False):
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(value, separators=(",", ":")))],
        structuredContent=value,
        isError=error,
    )


class Bridge:
    def __init__(self, nereus: Nereus):
        self.nereus = nereus
        self._watch_task = None
        self._fingerprint = None

    async def watch_changes(self, session):
        while True:
            await asyncio.sleep(15)
            try:
                payload = await self.nereus.request("GET", "/tools")
                fingerprint = json.dumps(payload["bindings"], sort_keys=True)
            except (BridgeError, KeyError, TypeError):
                fingerprint = None
            if fingerprint != self._fingerprint:
                self._fingerprint = fingerprint
                await session.send_tool_list_changed()

    async def list_tools(self, _context=None, _params=None):
        payload = await self.nereus.request("GET", "/tools")
        names = _bindings(payload)
        self._fingerprint = json.dumps(payload["bindings"], sort_keys=True)
        if _context is not None and self._watch_task is None:
            self._watch_task = asyncio.create_task(
                self.watch_changes(_context.session)
            )
        tools = [
            Tool(
                name=name, description=entries[0][1]["description"],
                inputSchema=entries[0][1]["inputSchema"],
            )
            for name, entries in sorted(names.items())
        ]
        tools.extend([
            Tool(
                name="pelagian_action_status",
                description="Check a pending Pelagian action.",
                inputSchema={
                    "type": "object", "additionalProperties": False,
                    "properties": {"call_id": {"type": "string"}},
                    "required": ["call_id"],
                },
            ),
            Tool(
                name="pelagian_resume_action",
                description="Resume an approved and confirmed Pelagian action.",
                inputSchema={
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "call_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["call_id", "arguments"],
                },
            ),
        ])
        if any(name in names for name in ("pelagian_action_status", "pelagian_resume_action")):
            raise BridgeError()
        return ListToolsResult(tools=tools)

    async def call_tool(self, _context, params):
        try:
            name = params.name
            arguments = params.arguments or {}
            if name == "pelagian_action_status":
                return _result(await self.nereus.request(
                    "GET", f"/calls/{_call_id(arguments['call_id'])}"
                ))
            if name == "pelagian_resume_action":
                return _result(await self.nereus.request(
                    "POST", f"/calls/{_call_id(arguments['call_id'])}/execute",
                    body={"arguments": arguments["arguments"]},
                ))
            names = _bindings(await self.nereus.request("GET", "/tools"))
            entries = names.get(name, [])
            record_id = arguments.get("record_id")
            eligible = sorted(
                (binding for binding, tool in entries
                 if record_id in tool.get("record_ids", binding["record_ids"])),
                key=lambda binding: binding["grant_id"],
            )
            if not eligible:
                raise BridgeError(403)
            binding = eligible[0]
            tool = entries[0][1]
            receipt = await self.nereus.request(
                "POST", "/calls",
                body={
                    "grant_id": binding["grant_id"],
                    "tool_id": tool["id"],
                    "arguments": arguments,
                },
                key=uuid4().hex,
            )
            if receipt["next_action"] == "execute":
                return _result(await self.nereus.request(
                    "POST", f"/calls/{receipt['call_id']}/execute",
                    body={"arguments": arguments},
                ))
            return _result(receipt)
        except BridgeError as exc:
            if exc.status in (401, 403):
                try:
                    await self.nereus.request("GET", "/tools")
                except BridgeError:
                    pass
            return _result(
                {"error": "Pelagian action unavailable", "status": exc.status},
                error=True,
            )
        except (KeyError, TypeError):
            return _result({"error": "Invalid tool arguments"}, error=True)


async def serve():
    nereus = Nereus()
    bridge = Bridge(nereus)
    server = Server(
        "pelagian-nereus", version="0.1.0",
        on_list_tools=bridge.list_tools, on_call_tool=bridge.call_tool,
    )
    async with stdio_server() as (read_stream, write_stream):
        try:
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(NotificationOptions(tools_changed=True)),
            )
        finally:
            if bridge._watch_task is not None:
                bridge._watch_task.cancel()


if __name__ == "__main__":
    asyncio.run(serve())
