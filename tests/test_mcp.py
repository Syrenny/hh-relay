import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from hh_relay import mcp_server
from hh_relay.models import SaveClassifiedVacanciesResult

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.json"
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
    assert [tool["name"] for tool in tools] == [
        "search_vacancies",
        "get_vacancy",
        "save_classified_vacancies",
    ]
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools[:2])
    assert tools[2]["annotations"]["readOnlyHint"] is False
    assert tools[2]["annotations"]["idempotentHint"] is True
    vacancies_schema = tools[2]["inputSchema"]["properties"]["vacancies"]
    assert vacancies_schema["minItems"] == 1
    assert vacancies_schema["maxItems"] == 15
    assert all(not tool["annotations"]["destructiveHint"] for tool in tools)


def test_mcp_calls_search_tool_with_structured_output(
    mcp_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        payload = json.loads(FIXTURE_PATH.read_text())
        payload["items"] = payload["items"][:1]
        payload["items"][0]["published_at"] = request.url.params["date_to"]
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)

    @asynccontextmanager
    async def create_mock_client() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    monkeypatch.setenv("HH_ACCESS_TOKEN", "token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://database")
    monkeypatch.setattr(mcp_server, "create_http_client", create_mock_client)
    monkeypatch.setattr(mcp_server, "known_vacancy_ids", AsyncMock(return_value=set()))

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


def test_mcp_search_filters_vacancies_already_in_database(
    mcp_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(FIXTURE_PATH.read_text())
        payload["items"] = payload["items"][:1]
        payload["items"][0]["published_at"] = request.url.params["date_to"]
        return httpx.Response(200, json=payload)

    @asynccontextmanager
    async def create_mock_client() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    monkeypatch.setenv("HH_ACCESS_TOKEN", "token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://database")
    monkeypatch.setattr(mcp_server, "create_http_client", create_mock_client)
    monkeypatch.setattr(
        mcp_server, "known_vacancy_ids", AsyncMock(return_value={"101"})
    )

    called = rpc(
        mcp_client,
        "tools/call",
        {"name": "search_vacancies", "arguments": {"text": "Python"}},
    )

    assert called["result"]["structuredContent"]["count"] == 0
    assert called["result"]["structuredContent"]["vacancies"] == []


def test_mcp_calls_save_tool_with_structured_output(
    mcp_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = AsyncMock(return_value=SaveClassifiedVacanciesResult(created=[101]))
    monkeypatch.setenv("DATABASE_URL", "postgresql://database")
    monkeypatch.setattr(mcp_server, "save_classifications", save)

    called = rpc(
        mcp_client,
        "tools/call",
        {
            "name": "save_classified_vacancies",
            "arguments": {
                "vacancies": [
                    {
                        "vacancy_id": 101,
                        "tier": "S",
                        "rationale": "Сильное совпадение",
                        "requirements": ["Python"],
                        "warnings": [],
                    }
                ]
            },
        },
    )

    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"]["created"] == [101]
    selections = save.await_args.args[2]
    assert selections[0].tier == "S"
