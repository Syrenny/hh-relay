from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from hh_relay import dashboard


def test_dashboard_requires_authentication(asgi_client: TestClient) -> None:
    response = asgi_client.get("/dashboard")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_dashboard_renders_component_ui(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(dashboard, "list_vacancies", AsyncMock(return_value=[]))

    response = asgi_client.get("/dashboard", auth=("ilya", "secret"))

    assert response.status_code == 200
    assert "@awesome.me/webawesome@3.14.0" in response.text
    assert "Здесь пока пусто" in response.text


def test_status_change_rejects_cross_origin_request(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")

    response = asgi_client.post(
        "/dashboard/vacancies/101/status",
        auth=("ilya", "secret"),
        headers={"Origin": "https://attacker.example"},
        data={"vacancy_status": "applied"},
    )

    assert response.status_code == 403


def test_status_change_updates_vacancy(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    update = AsyncMock(return_value=True)
    monkeypatch.setattr(dashboard, "update_vacancy_status", update)

    response = asgi_client.post(
        "/dashboard/vacancies/101/status",
        auth=("ilya", "secret"),
        headers={
            "Origin": "http://testserver",
            "Referer": "http://testserver/dashboard",
        },
        data={"vacancy_status": "applied"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    update.assert_awaited_once_with("postgresql://unused", "101", "applied")
