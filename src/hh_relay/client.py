import asyncio
import logging
import os
from datetime import datetime
from time import monotonic
from typing import Final
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from hh_relay.errors import (
    OAuthConfigurationError,
    OAuthTokenError,
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
    HHTokenResponse,
    HHVacancyDetail,
)

HH_API_URL: Final = "https://api.hh.ru"
HH_TOKEN_URL: Final = f"{HH_API_URL}/token"
HH_USER_AGENT: Final = "hh-relay/1.0 (https://github.com/Syrenny/hh-relay)"
MAX_ATTEMPTS: Final = 2
RETRY_DELAY_SECONDS: Final = 0.2
logger = logging.getLogger(__name__)


class ApplicationTokenManager:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_token(self, http_client: httpx.AsyncClient) -> str:
        if self._is_valid():
            return self._token or ""  # pragma: no cover
        async with self._lock:
            if self._is_valid():
                return self._token or ""  # pragma: no cover
            return await self._request_token(http_client)

    async def invalidate(self, token: str) -> None:
        async with self._lock:
            if self._token == token:
                self._token = None
                self._expires_at = None

    def _is_valid(self) -> bool:
        return self._token is not None and (
            self._expires_at is None or monotonic() < self._expires_at
        )

    async def _request_token(self, http_client: httpx.AsyncClient) -> str:
        client_id = self._client_id or os.getenv("HH_CLIENT_ID")
        client_secret = self._client_secret or os.getenv("HH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise OAuthConfigurationError
        try:
            response = await http_client.post(
                HH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
        except httpx.HTTPError as error:
            _log_transport_error("hh_token_error", error, HH_TOKEN_URL, 1)
            raise OAuthTokenError from error
        if response.is_error:
            logger.warning(
                "hh_token_response path=%s status=%d attempt=1",
                response.request.url.path,
                response.status_code,
            )
            raise OAuthTokenError
        try:
            payload = HHTokenResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise OAuthTokenError from error
        if payload.token_type.casefold() != "bearer":
            raise OAuthTokenError
        self._token = payload.access_token
        if payload.expires_in is not None:
            refresh_after = max(payload.expires_in * 0.9, payload.expires_in - 30)
            self._expires_at = monotonic() + refresh_after
        return payload.access_token


shared_token_manager = ApplicationTokenManager()


class HHClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        token_manager: ApplicationTokenManager = shared_token_manager,
    ) -> None:
        self._http_client = http_client
        self._token_manager = token_manager

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
        token = await self._token_manager.get_token(self._http_client)
        response = await self._request(path, token=token, params=params)
        if response.status_code == httpx.codes.UNAUTHORIZED:
            await self._token_manager.invalidate(token)
            token = await self._token_manager.get_token(self._http_client)
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
