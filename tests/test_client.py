import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from hh_relay.client import HH_USER_AGENT, ApplicationTokenManager, HHClient
from hh_relay.errors import (
    OAuthConfigurationError,
    OAuthTokenError,
    UpstreamForbiddenError,
    UpstreamRateLimitError,
    UpstreamTimeoutError,
    UpstreamUnauthorizedError,
    VacancyNotFoundError,
)
from hh_relay.models import Experience

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "search.json").read_text())
NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


def token_manager() -> ApplicationTokenManager:
    return ApplicationTokenManager(
        client_id="client",
        client_secret="secret",  # noqa: S106
    )


async def search(client: HHClient, *, text: str = "Python") -> object:
    return await client.search_page(
        text=text,
        area=1,
        experience=Experience.BETWEEN_ONE_AND_THREE,
        page=2,
        per_page=100,
        date_from=NOW.replace(day=24),
        date_to=NOW,
    )


@pytest.mark.asyncio
async def test_search_authorizes_and_passes_supported_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["HH-User-Agent"] == HH_USER_AGENT
        if request.url.path == "/token":
            assert request.headers["Content-Type"].startswith(
                "application/x-www-form-urlencoded"
            )
            assert request.content == (
                b"grant_type=client_credentials&client_id=client&client_secret=secret"
            )
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        assert request.headers["Authorization"] == "Bearer token"
        assert request.url.params["text"] == "Python"
        assert request.url.params["area"] == "1"
        assert request.url.params["experience"] == "between1And3"
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == "100"
        assert request.url.params["order_by"] == "publication_time"
        assert request.url.params["date_from"] == "2026-08-24T14:00:00+00:00"
        return httpx.Response(200, json=FIXTURE)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"HH-User-Agent": HH_USER_AGENT},
    ) as http:
        result = await search(HHClient(http, token_manager()))
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_parallel_requests_fetch_token_once() -> None:
    token_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/token":
            token_calls += 1
            await asyncio.sleep(0)
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        return httpx.Response(200, json=FIXTURE)

    manager = token_manager()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HHClient(http, manager)
        await asyncio.gather(*(search(client) for _ in range(5)))
    assert token_calls == 1


@pytest.mark.asyncio
async def test_unauthorized_refreshes_once() -> None:
    tokens = iter(["old", "new"])
    token_calls = 0
    api_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_calls, token_calls
        if request.url.path == "/token":
            token_calls += 1
            return httpx.Response(
                200,
                json={"access_token": next(tokens), "token_type": "bearer"},
            )
        api_calls += 1
        if request.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        return httpx.Response(200, json=FIXTURE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await search(HHClient(http, token_manager()))
    assert token_calls == 2
    assert api_calls == 2


@pytest.mark.asyncio
async def test_second_unauthorized_is_controlled_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamUnauthorizedError):
            await search(HHClient(http, token_manager()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(403, UpstreamForbiddenError), (429, UpstreamRateLimitError)],
)
async def test_maps_api_statuses(status: int, error_type: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(error_type):
            await search(HHClient(http, token_manager()))


@pytest.mark.asyncio
async def test_timeout_log_does_not_expose_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamTimeoutError):
            await search(HHClient(http, token_manager()), text="secret search text")
    assert caplog.text.count("hh_request_timeout") == 2
    assert "path=/vacancies" in caplog.text
    assert "secret search text" not in caplog.text
    assert "Bearer" not in caplog.text


@pytest.mark.asyncio
async def test_missing_config_and_oauth_rejection_are_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HH_CLIENT_ID", raising=False)
    monkeypatch.delenv("HH_CLIENT_SECRET", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as http:
        with pytest.raises(OAuthConfigurationError):
            await search(HHClient(http, ApplicationTokenManager()))
        with pytest.raises(OAuthTokenError):
            await search(HHClient(http, token_manager()))


@pytest.mark.asyncio
async def test_get_vacancy_maps_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "token", "token_type": "bearer"}
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(VacancyNotFoundError):
            await HHClient(http, token_manager()).get_vacancy(999)
