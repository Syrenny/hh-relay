import asyncio
import logging
from typing import Final

import httpx

from hh_relay.errors import (
    UpstreamForbiddenError,
    UpstreamHTTPError,
    UpstreamTimeoutError,
    VacancyNotFoundError,
)
from hh_relay.models import (
    Experience,
    UpstreamSearchResult,
    UpstreamVacancyDetail,
)
from hh_relay.parser import extract_search_result, extract_vacancy_detail

HH_SEARCH_URL: Final = "https://hh.ru/search/vacancy"
MAX_ATTEMPTS: Final = 2
RETRY_DELAY_SECONDS: Final = 0.2
logger = logging.getLogger(__name__)
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

    async def search_page(
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        page: int,
    ) -> UpstreamSearchResult:
        params: dict[str, str | int] = {
            "text": text,
            "page": page,
            "enable_snippets": "true",
            "order_by": "publication_time",
        }
        if area is not None:
            params["area"] = area
        if experience is not None:
            params["experience"] = experience.value

        response = await self._get(HH_SEARCH_URL, params=params)
        return extract_search_result(response.text).vacancy_search_result

    async def get_vacancy(self, vacancy_id: int) -> UpstreamVacancyDetail:
        response = await self._get(
            f"https://hh.ru/vacancy/{vacancy_id}",
            vacancy_not_found=True,
        )
        return extract_vacancy_detail(response.text)

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        vacancy_not_found: bool = False,
    ) -> httpx.Response:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._http_client.get(url, params=params)
            except httpx.TimeoutException as error:
                logger.warning(
                    "hh_request_timeout url=%s attempt=%d/%d timeout_type=%s",
                    _safe_error_url(error, fallback=url),
                    attempt + 1,
                    MAX_ATTEMPTS,
                    type(error).__name__,
                )
                if attempt + 1 == MAX_ATTEMPTS:
                    raise UpstreamTimeoutError from error
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            except httpx.HTTPError as error:
                logger.warning(
                    "hh_request_error url=%s attempt=%d/%d error_type=%s",
                    _safe_error_url(error, fallback=url),
                    attempt + 1,
                    MAX_ATTEMPTS,
                    type(error).__name__,
                )
                if attempt + 1 == MAX_ATTEMPTS:
                    raise UpstreamHTTPError from error
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue

            if (
                _is_retryable_status(response.status_code)
                and attempt + 1 < MAX_ATTEMPTS
            ):
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            break
        else:  # pragma: no cover
            raise UpstreamHTTPError

        if response.status_code == httpx.codes.NOT_FOUND and vacancy_not_found:
            raise VacancyNotFoundError
        if response.status_code == httpx.codes.FORBIDDEN:
            raise UpstreamForbiddenError
        if response.is_error:
            raise UpstreamHTTPError
        return response


def _is_retryable_status(status_code: int) -> bool:
    return (
        status_code
        in {
            httpx.codes.FORBIDDEN,
            httpx.codes.TOO_MANY_REQUESTS,
        }
        or status_code >= httpx.codes.INTERNAL_SERVER_ERROR
    )


def _safe_error_url(error: httpx.HTTPError, *, fallback: str) -> str:
    try:
        request_url = error.request.url
    except RuntimeError:
        request_url = httpx.URL(fallback)
    return str(request_url.copy_with(query=None, fragment=None))


def create_http_client(*, proxy: str | None = None) -> httpx.AsyncClient:
    timeout = httpx.Timeout(15.0, connect=5.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    return httpx.AsyncClient(
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        limits=limits,
        proxy=proxy,
        timeout=timeout,
    )
