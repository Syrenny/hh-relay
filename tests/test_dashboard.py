from datetime import UTC, datetime
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
    assert "Новых вакансий пока нет" in response.text
    assert "Показать скрытые" in response.text
    assert "<wa-button" not in response.text


def test_dashboard_can_show_hidden_vacancies(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    vacancies = [
        {
            "id": vacancy_id,
            "user_status": vacancy_status,
            "name": vacancy_id,
            "tier": "A",
            "published_at": datetime(2026, 11, 2, tzinfo=UTC),
            "employer": None,
            "salary": None,
            "area": None,
            "rationale": None,
            "url": f"https://example.com/{vacancy_id}",
        }
        for vacancy_id, vacancy_status in (
            ("visible", "new"),
            ("hidden", "archived"),
        )
    ]
    monkeypatch.setattr(dashboard, "list_vacancies", AsyncMock(return_value=vacancies))

    response = asgi_client.get("/dashboard?show_hidden=true", auth=("ilya", "secret"))

    assert response.status_code == 200
    assert "Скрытые вакансии" in response.text
    assert 'action="/dashboard/vacancies/hidden/status"' in response.text
    assert 'action="/dashboard/vacancies/visible/status"' not in response.text


def test_dashboard_orders_vacancies_by_tier(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    vacancies = [
        {
            "id": tier,
            "user_status": "new",
            "name": f"Tier {tier}",
            "tier": tier,
            "published_at": datetime(2026, 11, 6, tzinfo=UTC),
            "employer": None,
            "salary": None,
            "area": None,
            "rationale": None,
            "url": f"https://example.com/{tier}",
        }
        for tier in ("C", "rejected", "A", "S", "B")
    ]
    monkeypatch.setattr(dashboard, "list_vacancies", AsyncMock(return_value=vacancies))

    response = asgi_client.get("/dashboard", auth=("ilya", "secret"))

    positions = [response.text.index(f"Tier {tier}") for tier in ("S", "A", "B", "C")]
    assert positions == sorted(positions)
    assert "Tier rejected" not in response.text


def test_hidden_dashboard_includes_rejected_vacancies(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    vacancies = [
        {
            "id": "rejected",
            "user_status": "new",
            "name": "Rejected vacancy",
            "tier": "rejected",
            "published_at": datetime(2026, 11, 6, tzinfo=UTC),
            "employer": None,
            "salary": None,
            "area": None,
            "rationale": "Does not match the candidate profile.",
            "url": "https://example.com/rejected",
        }
    ]
    monkeypatch.setattr(dashboard, "list_vacancies", AsyncMock(return_value=vacancies))

    response = asgi_client.get("/dashboard?show_hidden=true", auth=("ilya", "secret"))

    assert response.status_code == 200
    assert "Rejected vacancy" in response.text
    assert "tier-rejected" in response.text
    assert 'action="/dashboard/vacancies/rejected/status"' not in response.text


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
        data={"vacancy_status": "archived"},
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
        data={"vacancy_status": "archived"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    update.assert_awaited_once_with("postgresql://unused", "101", "archived")


def test_archive_all_vacancies(
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "ilya")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    archive_all = AsyncMock(return_value=3)
    monkeypatch.setattr(dashboard, "archive_visible_vacancies", archive_all)

    response = asgi_client.post(
        "/dashboard/vacancies/archive-all",
        auth=("ilya", "secret"),
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    archive_all.assert_awaited_once_with("postgresql://unused")
