from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse

from hh_relay.action_schema import build_action_schema
from hh_relay.client import HHClient
from hh_relay.errors import RelayError
from hh_relay.mcp_server import mcp_http_app
from hh_relay.models import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    ProxyHealthResponse,
    SearchQuery,
    SearchResponse,
    VacancyDetail,
)
from hh_relay.service import VacancyService
from hh_relay.sing_box import (
    SingBoxManager,
    probe_hh_via_proxy,
    proxy_http_client,
    shared_sing_box_manager,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.sing_box_manager = shared_sing_box_manager
    try:
        async with mcp_http_app.router.lifespan_context(mcp_http_app):
            yield
    finally:
        await shared_sing_box_manager.close()


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


async def get_hh_client(request: Request) -> AsyncIterator[HHClient]:
    manager: SingBoxManager = request.app.state.sing_box_manager
    async with proxy_http_client(manager) as http_client:
        yield HHClient(http_client)


def get_now() -> datetime:
    return datetime.now(UTC)


def get_sing_box_manager(request: Request) -> SingBoxManager:
    return request.app.state.sing_box_manager


HHClientDependency = Annotated[HHClient, Depends(get_hh_client)]
NowDependency = Annotated[datetime, Depends(get_now)]
SingBoxManagerDependency = Annotated[SingBoxManager, Depends(get_sing_box_manager)]


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
    "/api/proxy-health",
    summary="Проверить доступ к hh.ru через sing-box",
    include_in_schema=False,
)
async def proxy_health(manager: SingBoxManagerDependency) -> ProxyHealthResponse:
    return await probe_hh_via_proxy(manager)


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
