import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from hh_relay.client import HH_USER_AGENT, HHClient
from hh_relay.errors import (
    OAuthConfigurationError,
    UpstreamForbiddenError,
    UpstreamRateLimitError,
    UpstreamTimeoutError,
    UpstreamUnauthorizedError,
    VacancyNotFoundError,
)
from hh_relay.models import Experience

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "search.json").read_text())
NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


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
        result = await search(HHClient(http, "token"))
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_parallel_clients_never_request_token() -> None:
    api_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_calls
        assert request.url.path == "/vacancies"
        assert request.headers["Authorization"] == "Bearer token"
        api_calls += 1
        await asyncio.sleep(0)
        return httpx.Response(200, json=FIXTURE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await asyncio.gather(*(search(HHClient(http, "token")) for _ in range(8)))
    assert api_calls == 8


@pytest.mark.asyncio
async def test_unauthorized_does_not_rotate_or_retry() -> None:
    api_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_calls
        assert request.url.path == "/vacancies"
        assert request.headers["Authorization"] == "Bearer token"
        api_calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamUnauthorizedError):
            await search(HHClient(http, "token"))
    assert api_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(403, UpstreamForbiddenError), (429, UpstreamRateLimitError)],
)
async def test_maps_api_statuses(status: int, error_type: type[Exception]) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(error_type):
            await search(HHClient(http, "token"))


@pytest.mark.asyncio
async def test_timeout_log_does_not_expose_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamTimeoutError):
            await search(HHClient(http, "token"), text="secret search text")
    assert caplog.text.count("hh_request_timeout") == 2
    assert "path=/vacancies" in caplog.text
    assert "secret search text" not in caplog.text
    assert "Bearer" not in caplog.text


@pytest.mark.asyncio
async def test_missing_config_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HH_ACCESS_TOKEN", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as http:
        with pytest.raises(OAuthConfigurationError):
            await search(HHClient(http))


@pytest.mark.asyncio
async def test_get_vacancy_maps_not_found() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(VacancyNotFoundError):
            await HHClient(http, "token").get_vacancy(999)
