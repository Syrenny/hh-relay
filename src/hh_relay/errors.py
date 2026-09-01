from dataclasses import dataclass


@dataclass(slots=True)
class RelayError(Exception):
    code: str
    message: str
    status_code: int


class OAuthConfigurationError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="oauth_not_configured",
            message="hh.ru OAuth credentials are not configured",
            status_code=503,
        )


class OAuthTokenError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="oauth_token_error",
            message="hh.ru application authorization failed",
            status_code=502,
        )


class UpstreamUnauthorizedError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_unauthorized",
            message="hh.ru rejected application authorization",
            status_code=502,
        )


class UpstreamForbiddenError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_forbidden",
            message="hh.ru forbids access to this resource",
            status_code=502,
        )


class UpstreamRateLimitError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_rate_limited",
            message="hh.ru request limit was exceeded",
            status_code=502,
        )


class UpstreamTimeoutError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_timeout",
            message="hh.ru did not respond in time",
            status_code=504,
        )


class UpstreamHTTPError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_http_error",
            message="hh.ru returned an unexpected response",
            status_code=502,
        )


class UpstreamStructureError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_structure_changed",
            message="hh.ru response structure is not supported",
            status_code=502,
        )


class VacancyNotFoundError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="vacancy_not_found",
            message="Vacancy was not found on hh.ru",
            status_code=404,
        )
