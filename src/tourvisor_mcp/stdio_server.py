"""Dependency-light MCP stdio server.

The official MCP Python SDK (and FastMCP) pulls in ``mcp_types``, ``starlette``
and ``pydantic``, which costs 3–5 seconds to import on a 1-vCPU box.  Some MCP
hosts (e.g. PicoClaw) enforce a short connect deadline, so this module speaks the
MCP JSON-RPC protocol directly over stdin/stdout, importing the heavy search /
HTTP dependencies only when a tool is actually invoked.

This gives an ``initialize`` + ``tools/list`` round trip in well under a second
while exposing exactly the same three tools as :mod:`tourvisor_mcp.server`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "tourvisor"
SERVER_VERSION = "0.1.0"

INSTRUCTIONS = (
    "Search package tours on tourvisor.ru. Use resolve_filters first if you are "
    "unsure about country/resort/departure/meal ids, then call search_tours. "
    "Data comes from Tourvisor's public (unofficial) endpoints, so results may "
    "be rate-limited."
)


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(msg_id: Any, result: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


async def _handle(msg: dict[str, Any]) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")

    # Notifications (no id) never get a reply.
    if msg_id is None:
        return

    if method == "initialize":
        _result(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            },
        )
        return

    if method == "ping":
        _result(msg_id, {})
        return

    if method == "tools/list":
        # Imported lazily; the schema module only needs the (light) stdlib.
        from .tools import TOOL_SCHEMAS

        _result(msg_id, {"tools": TOOL_SCHEMAS})
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        # Heavy deps (httpx and our search stack) are imported on first call.
        from .tools import call_tool

        try:
            text = await call_tool(name, arguments)
            is_error = False
            try:
                is_error = bool(json.loads(text).get("error"))
            except (json.JSONDecodeError, AttributeError):
                is_error = False
            _result(
                msg_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_error,
                },
            )
        except Exception as exc:  # noqa: BLE001 - reported back to the client
            _result(
                msg_id,
                {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                    "isError": True,
                },
            )
        return

    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        _result(msg_id, {key: []})
        return

    _error(msg_id, -32601, f"Method not found: {method}")


async def _serve() -> None:
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            await _handle(msg)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            if isinstance(msg, dict) and msg.get("id") is not None:
                _error(msg["id"], -32603, str(exc))


def main() -> None:
    try:
        asyncio.run(_serve())
    except (KeyboardInterrupt, BrokenPipeError):
        pass


if __name__ == "__main__":
    main()
