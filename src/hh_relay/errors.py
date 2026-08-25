from dataclasses import dataclass


@dataclass(slots=True)
class RelayError(Exception):
    code: str
    message: str
    status_code: int


class UpstreamForbiddenError(RelayError):
    def __init__(self) -> None:
        super().__init__(
            code="upstream_forbidden",
            message="hh.ru rejected the request",
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
