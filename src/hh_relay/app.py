from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse

from hh_relay.action_schema import build_action_schema
from hh_relay.client import HHClient, create_http_client
from hh_relay.errors import RelayError
from hh_relay.mcp_server import mcp_http_app
from hh_relay.models import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    SearchQuery,
    SearchResponse,
    VacancyDetail,
)
from hh_relay.service import VacancyService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with (
        create_http_client() as http_client,
        mcp_http_app.router.lifespan_context(mcp_http_app),
    ):
        app.state.hh_client = HHClient(http_client)
        yield


app = FastAPI(
    title="hh.ru Vacancy Relay",
    description=(
        "Поиск вакансий за последние 24 часа и полные карточки через SSR hh.ru "
        "без использования api.hh.ru."
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
        "Самостоятельно обходит страницы и возвращает нормализованные вакансии, "
        "опубликованные за последние 24 часа, без дублей по ID."
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
    return await VacancyService(client).search(
        text=query.text,
        area=query.area,
        experience=query.experience,
        now=now,
    )


@app.get(
    "/api/vacancies/{vacancy_id}",
    operation_id="getVacancy",
    summary="Получить полную карточку вакансии",
    description="Возвращает полное HTML-описание и детали вакансии от hh.ru.",
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def get_vacancy(
    client: HHClientDependency,
    vacancy_id: Annotated[int, Path(ge=1)],
) -> VacancyDetail:
    return await VacancyService(client).get_vacancy(vacancy_id)


app.openapi = build_action_schema
app.mount("/", mcp_http_app)
