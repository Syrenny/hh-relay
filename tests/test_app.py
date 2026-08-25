from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from hh_relay.app import app, get_hh_client, get_now
from hh_relay.client import HHClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.html"


@pytest.fixture
def client() -> TestClient:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, text=FIXTURE_PATH.read_text()),
    )
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
        params={"text": "Python", "area": 1, "hours": 24},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["vacancies"][0]["id"] == "101"
    assert body["vacancies"][0]["salary"]["from"] == 200000


def test_search_validates_query(client: TestClient) -> None:
    response = client.get(
        "/api/vacancies/search",
        params={"text": "", "page": -1, "hours": 0},
    )

    assert response.status_code == 422
