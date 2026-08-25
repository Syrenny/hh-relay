from pathlib import Path

import httpx
import pytest

from hh_relay.client import HHClient
from hh_relay.errors import (
    UpstreamForbiddenError,
    UpstreamHTTPError,
    UpstreamTimeoutError,
    VacancyNotFoundError,
)
from hh_relay.models import Experience

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.html"


@pytest.mark.asyncio
async def test_search_passes_supported_parameters() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["text"] == "Python"
        assert request.url.params["area"] == "1"
        assert request.url.params["experience"] == "between1And3"
        assert request.url.params["page"] == "2"
        assert request.url.params["enable_snippets"] == "true"
        assert request.url.params["order_by"] == "publication_time"
        return httpx.Response(200, text=FIXTURE_PATH.read_text())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await HHClient(http).search_page(
            text="Python",
            area=1,
            experience=Experience.BETWEEN_ONE_AND_THREE,
            page=2,
        )

    assert len(result.vacancies) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (403, UpstreamForbiddenError),
        (500, UpstreamHTTPError),
    ],
)
async def test_search_maps_upstream_statuses(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code),
    )
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(expected_error):
            await HHClient(http).search_page(
                text="Python",
                area=None,
                experience=None,
                page=0,
            )


@pytest.mark.asyncio
async def test_search_maps_timeout() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        with pytest.raises(UpstreamTimeoutError):
            await HHClient(http).search_page(
                text="Python",
                area=None,
                experience=None,
                page=0,
            )


@pytest.mark.asyncio
async def test_get_vacancy_maps_not_found() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(VacancyNotFoundError):
            await HHClient(http).get_vacancy(999)


@pytest.mark.asyncio
async def test_search_retries_transient_forbidden() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(403)
        return httpx.Response(200, text=FIXTURE_PATH.read_text())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await HHClient(http).search_page(
            text="Python",
            area=None,
            experience=None,
            page=0,
        )

    assert attempts == 2
    assert len(result.vacancies) == 3
