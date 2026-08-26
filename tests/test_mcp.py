from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from hh_relay import mcp_server

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.html"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture
def mcp_client(asgi_client: TestClient) -> TestClient:
    return asgi_client


def rpc(client: TestClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )

    assert response.status_code == 200
    return response.json()


def test_mcp_initialize_and_list_tools(mcp_client: TestClient) -> None:
    initialized = rpc(
        mcp_client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    )
    listed = rpc(mcp_client, "tools/list", {})

    assert initialized["result"]["serverInfo"]["name"] == "hh.ru Vacancy Relay"
    tools = listed["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["search_vacancies", "get_vacancy"]
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    assert all(not tool["annotations"]["destructiveHint"] for tool in tools)


def test_mcp_calls_search_tool_with_structured_output(
    mcp_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, text=FIXTURE_PATH.read_text()),
    )

    @asynccontextmanager
    async def create_mock_client() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    monkeypatch.setattr(mcp_server, "proxy_http_client", create_mock_client)

    called = rpc(
        mcp_client,
        "tools/call",
        {
            "name": "search_vacancies",
            "arguments": {"text": "Python", "area": 1},
        },
    )

    assert called["result"]["isError"] is False
    structured = called["result"]["structuredContent"]
    assert structured["count"] == 1
    assert structured["vacancies"][0]["id"] == "101"
    assert structured["vacancies"][0]["salary"]["from"] == 200000
    assert "snippet" not in structured["vacancies"][0]
