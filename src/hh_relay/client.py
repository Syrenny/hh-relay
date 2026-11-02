import asyncio
import logging
import os
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from hh_relay.errors import (
    OAuthConfigurationError,
    UpstreamForbiddenError,
    UpstreamHTTPError,
    UpstreamRateLimitError,
    UpstreamStructureError,
    UpstreamTimeoutError,
    UpstreamUnauthorizedError,
    VacancyNotFoundError,
)
from hh_relay.models import (
    Experience,
    HHSearchResponse,
    HHVacancyDetail,
)

HH_API_URL: Final = "https://api.hh.ru"
HH_USER_AGENT: Final = "hh-relay/1.0 (https://github.com/Syrenny/hh-relay)"
MAX_ATTEMPTS: Final = 2
RETRY_DELAY_SECONDS: Final = 0.2
logger = logging.getLogger(__name__)


class HHClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        access_token: str | None = None,
    ) -> None:
        self._http_client = http_client
        self._access_token = access_token

    async def search_page(  # noqa: PLR0913
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        page: int,
        per_page: int,
        date_from: datetime,
        date_to: datetime,
    ) -> HHSearchResponse:
        params: dict[str, str | int] = {
            "text": text,
            "page": page,
            "per_page": per_page,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "order_by": "publication_time",
        }
        if area is not None:
            params["area"] = area
        if experience is not None:
            params["experience"] = experience.value
        response = await self._get("/vacancies", params=params)
        try:
            return HHSearchResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise UpstreamStructureError from error

    async def get_vacancy(self, vacancy_id: int) -> HHVacancyDetail:
        response = await self._get(f"/vacancies/{vacancy_id}", vacancy_not_found=True)
        try:
            return HHVacancyDetail.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise UpstreamStructureError from error

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        vacancy_not_found: bool = False,
    ) -> httpx.Response:
        token = self._access_token or os.getenv("HH_ACCESS_TOKEN")
        if not token:
            raise OAuthConfigurationError
        response = await self._request(path, token=token, params=params)
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise UpstreamUnauthorizedError
        if response.status_code == httpx.codes.NOT_FOUND and vacancy_not_found:
            raise VacancyNotFoundError
        if response.status_code == httpx.codes.FORBIDDEN:
            raise UpstreamForbiddenError
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise UpstreamRateLimitError
        if response.is_error:
            raise UpstreamHTTPError
        return response

    async def _request(
        self,
        path: str,
        *,
        token: str,
        params: dict[str, str | int] | None,
    ) -> httpx.Response:
        url = f"{HH_API_URL}{path}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http_client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.TimeoutException as error:
                _log_transport_error("hh_request_timeout", error, url, attempt)
                if attempt == MAX_ATTEMPTS:
                    raise UpstreamTimeoutError from error
            except httpx.HTTPError as error:
                _log_transport_error("hh_request_error", error, url, attempt)
                if attempt == MAX_ATTEMPTS:
                    raise UpstreamHTTPError from error
            else:
                if (
                    not _is_retryable_status(response.status_code)
                    or attempt == MAX_ATTEMPTS
                ):
                    return response
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        raise UpstreamHTTPError  # pragma: no cover


def _is_retryable_status(status_code: int) -> bool:
    return status_code >= httpx.codes.INTERNAL_SERVER_ERROR


def _log_transport_error(
    event: str,
    error: httpx.HTTPError,
    fallback_url: str,
    attempt: int,
) -> None:
    try:
        path = error.request.url.path
    except RuntimeError:
        path = urlsplit(fallback_url).path
    logger.warning(
        "%s path=%s attempt=%d/%d error_type=%s",
        event,
        path,
        attempt,
        MAX_ATTEMPTS,
        type(error).__name__,
    )


def create_http_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(15.0, connect=5.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    return httpx.AsyncClient(
        headers={"Accept": "application/json", "HH-User-Agent": HH_USER_AGENT},
        limits=limits,
        timeout=timeout,
    )
