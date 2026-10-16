"""Tests for the dependency-light stdio MCP server."""

from __future__ import annotations

import json

import pytest

from tourvisor_mcp import stdio_server
from tourvisor_mcp.tools import TOOL_SCHEMAS


def test_tool_schemas_present():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"resolve_filters", "search_tours", "list_reference"}
    search = next(t for t in TOOL_SCHEMAS if t["name"] == "search_tours")
    assert search["inputSchema"]["required"] == ["date_from", "date_to"]
    assert "services" in search["inputSchema"]["properties"]


async def test_initialize_handshake(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(stdio_server, "_send", lambda m: sent.append(m))
    await stdio_server._handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
    )
    assert len(sent) == 1
    result = sent[0]["result"]
    assert result["serverInfo"]["name"] == "tourvisor"
    assert "tools" in result["capabilities"]


async def test_tools_list(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(stdio_server, "_send", lambda m: sent.append(m))
    await stdio_server._handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = sent[0]["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "resolve_filters",
        "search_tours",
        "list_reference",
    }


async def test_unknown_method(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(stdio_server, "_send", lambda m: sent.append(m))
    await stdio_server._handle({"jsonrpc": "2.0", "id": 3, "method": "bogus/method"})
    assert sent[0]["error"]["code"] == -32601


async def test_notification_ignored(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(stdio_server, "_send", lambda m: sent.append(m))
    await stdio_server._handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert sent == []


async def test_tools_call_unknown_tool(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(stdio_server, "_send", lambda m: sent.append(m))
    await stdio_server._handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    payload = json.loads(sent[0]["result"]["content"][0]["text"])
    assert "error" in payload
    assert sent[0]["result"]["isError"] is True
