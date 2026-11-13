import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

import hh_relay.app as app_module
from hh_relay.app import app, get_hh_client, get_now
from hh_relay.client import HHClient
from hh_relay.models import SearchResponse, VacancySummary

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.json"
DETAIL_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "vacancy.json"


@pytest.fixture
def client(asgi_client: TestClient) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        fixture = (
            DETAIL_FIXTURE_PATH
            if request.url.path.startswith("/vacancies/")
            else FIXTURE_PATH
        )
        return httpx.Response(200, json=json.loads(fixture.read_text()))

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    app.dependency_overrides[get_hh_client] = lambda: HHClient(http_client, "token")
    app.dependency_overrides[get_now] = lambda: datetime(
        2026,
        8,
        25,
        14,
        tzinfo=UTC,
    )
    yield asgi_client
    asyncio.run(http_client.aclose())
    app.dependency_overrides.clear()


def test_health_does_not_call_upstream(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_normalized_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = AsyncMock(
        return_value=SearchResponse(
            count=1,
            total_count=1,
            vacancies=[
                VacancySummary(
                    id="101",
                    name="Python Developer",
                    url="https://hh.ru/vacancy/101",
                    salary={"from_": 200000},
                    published_at="2026-08-25T13:00:00Z",
                )
            ],
            queries_executed=14,
            pages_fetched=14,
            cutoff="2026-08-24T14:00:00Z",
        )
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://database")
    monkeypatch.setattr(app_module, "search_new_vacancies", search)
    response = client.get(
        "/api/vacancies/search",
        params={"cursor": "next"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["pages_fetched"] == 14
    assert body["cutoff"] == "2026-08-24T14:00:00Z"
    assert body["vacancies"][0]["id"] == "101"
    assert body["vacancies"][0]["salary"]["from"] == 200000
    assert "snippet" not in body["vacancies"][0]
    assert search.await_args.kwargs["cursor"] == "next"


def test_get_vacancy_returns_full_description(client: TestClient) -> None:
    response = client.get("/api/vacancies/101")

    assert response.status_code == 200
    assert response.json()["description"] == "<p>Full &amp; detailed description</p>"


def test_get_vacancy_returns_controlled_not_found(client: TestClient) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    app.dependency_overrides[get_hh_client] = lambda: HHClient(http_client, "token")

    response = client.get("/api/vacancies/999")

    asyncio.run(http_client.aclose())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


def test_openapi_exposes_only_public_search_parameters() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/vacancies/search"]["get"]

    assert [parameter["name"] for parameter in operation["parameters"]] == ["cursor"]
    assert operation["operationId"] == "searchVacancies"
    assert (
        schema["paths"]["/api/vacancies/{vacancy_id}"]["get"]["operationId"]
        == "getVacancy"
    )


def test_action_openapi_has_no_any_of() -> None:
    serialized_schema = json.dumps(app.openapi())

    assert '"anyOf"' not in serialized_schema
    assert '"$defs"' not in serialized_schema
