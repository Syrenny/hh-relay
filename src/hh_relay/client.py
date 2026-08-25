from typing import Final

import httpx

from hh_relay.errors import (
    UpstreamForbiddenError,
    UpstreamHTTPError,
    UpstreamTimeoutError,
)
from hh_relay.models import Experience, UpstreamVacancy
from hh_relay.parser import extract_vacancies

HH_SEARCH_URL: Final = "https://hh.ru/search/vacancy"
DEFAULT_HEADERS: Final = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
}


class HHClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def search(
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        page: int,
    ) -> list[UpstreamVacancy]:
        params: dict[str, str | int] = {
            "text": text,
            "page": page,
            "enable_snippets": "true",
        }
        if area is not None:
            params["area"] = area
        if experience is not None:
            params["experience"] = experience.value

        try:
            response = await self._http_client.get(HH_SEARCH_URL, params=params)
        except httpx.TimeoutException as error:
            raise UpstreamTimeoutError from error
        except httpx.HTTPError as error:
            raise UpstreamHTTPError from error

        if response.status_code == httpx.codes.FORBIDDEN:
            raise UpstreamForbiddenError
        if response.is_error:
            raise UpstreamHTTPError
        return extract_vacancies(response.text)


def create_http_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(15.0, connect=5.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    return httpx.AsyncClient(
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        limits=limits,
        timeout=timeout,
    )
