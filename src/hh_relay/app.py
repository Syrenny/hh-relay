from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from hh_relay.client import HHClient, create_http_client
from hh_relay.errors import RelayError
from hh_relay.models import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    SearchQuery,
    SearchResponse,
)
from hh_relay.parser import filter_recent_unique, normalize_vacancy


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with create_http_client() as http_client:
        app.state.hh_client = HHClient(http_client)
        yield


app = FastAPI(
    title="hh.ru Vacancy Relay",
    description=(
        "Поиск вакансий на hh.ru через SSR-страницу без использования api.hh.ru."
    ),
    version="0.1.0",
    lifespan=lifespan,
    servers=[{"url": "https://hh-relay.vercel.app"}],
)


def get_hh_client(request: Request) -> HHClient:
    return request.app.state.hh_client


def get_now() -> datetime:
    return datetime.now(UTC)


HHClientDependency = Annotated[HHClient, Depends(get_hh_client)]
NowDependency = Annotated[datetime, Depends(get_now)]


@app.exception_handler(RelayError)
async def relay_error_handler(_request: Request, error: RelayError) -> JSONResponse:
    response = ErrorResponse(
        error=ErrorDetail(code=error.code, message=error.message),
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )


@app.get(
    "/api/health",
    operation_id="healthCheck",
    summary="Проверить доступность сервиса",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/api/vacancies/search",
    operation_id="searchVacancies",
    summary="Найти свежие вакансии на hh.ru",
    description=(
        "Возвращает нормализованные вакансии, опубликованные за последние N часов, "
        "без дублей по ID."
    ),
    response_model_by_alias=True,
    responses={
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def search_vacancies(
    client: HHClientDependency,
    now: NowDependency,
    query: Annotated[SearchQuery, Query()],
) -> SearchResponse:
    upstream_vacancies = await client.search(
        text=query.text,
        area=query.area,
        experience=query.experience,
        page=query.page,
    )
    normalized = [normalize_vacancy(item) for item in upstream_vacancies]
    vacancies = filter_recent_unique(normalized, hours=query.hours, now=now)
    return SearchResponse(count=len(vacancies), vacancies=vacancies)
