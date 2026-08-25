import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from hh_relay.app import app, get_hh_client, get_now
from hh_relay.client import HHClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.html"
DETAIL_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "vacancy.html"


@pytest.fixture
def client() -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        fixture = (
            DETAIL_FIXTURE_PATH
            if request.url.path.startswith("/vacancy/")
            else FIXTURE_PATH
        )
        return httpx.Response(200, text=fixture.read_text())

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    app.dependency_overrides[get_hh_client] = lambda: HHClient(http_client)
    app.dependency_overrides[get_now] = lambda: datetime(
        2026,
        8,
        25,
        14,
        tzinfo=UTC,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_does_not_call_upstream(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_normalized_response(client: TestClient) -> None:
    response = client.get(
        "/api/vacancies/search",
        params={"text": "Python", "area": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["pages_fetched"] == 1
    assert body["truncated"] is False
    assert body["cutoff"] == "2026-08-24T14:00:00Z"
    assert body["vacancies"][0]["id"] == "101"
    assert body["vacancies"][0]["salary"]["from"] == 200000
    assert "snippet" not in body["vacancies"][0]


def test_search_validates_query(client: TestClient) -> None:
    response = client.get(
        "/api/vacancies/search",
        params={"text": ""},
    )

    assert response.status_code == 422


def test_get_vacancy_returns_full_description(client: TestClient) -> None:
    response = client.get("/api/vacancies/101")

    assert response.status_code == 200
    assert response.json()["description"] == "<p>Full &amp; detailed description</p>"


def test_get_vacancy_returns_controlled_not_found(client: TestClient) -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
    )
    app.dependency_overrides[get_hh_client] = lambda: HHClient(http_client)

    response = client.get("/api/vacancies/999")

    asyncio.run(http_client.aclose())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


def test_openapi_exposes_only_public_search_parameters() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/vacancies/search"]["get"]

    assert [parameter["name"] for parameter in operation["parameters"]] == [
        "text",
        "area",
        "experience",
    ]
    assert operation["operationId"] == "searchVacancies"
    assert (
        schema["paths"]["/api/vacancies/{vacancy_id}"]["get"]["operationId"]
        == "getVacancy"
    )


def test_action_openapi_has_no_any_of() -> None:
    serialized_schema = json.dumps(app.openapi())

    assert '"anyOf"' not in serialized_schema
    assert '"$defs"' not in serialized_schema
