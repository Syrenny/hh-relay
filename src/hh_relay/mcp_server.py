from datetime import UTC, datetime
from typing import Annotated, NoReturn

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from hh_relay.client import HHClient, create_http_client
from hh_relay.config import required_env
from hh_relay.errors import RelayError
from hh_relay.models import (
    ClassifiedVacancy,
    SaveClassifiedVacanciesResult,
    SearchResponse,
    VacancyDetail,
)
from hh_relay.search_flow import search_new_vacancies
from hh_relay.selection_service import save_classified_vacancies as save_classifications
from hh_relay.service import VacancyService

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

mcp = FastMCP(
    name="hh.ru Vacancy Relay",
    instructions=(
        "Получите все страницы вакансий через search_vacancies, передавая только "
        "возвращённый next_cursor. "
        "Вызывайте get_vacancy только для выбранных ID, когда нужно полное описание. "
        "Классифицируйте все обработанные вакансии и сохраняйте результат через "
        "save_classified_vacancies, добавляя rejected для неподходящих позиций."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool(
    name="search_vacancies",
    title="Поиск свежих вакансий hh.ru",
    description=(
        "Выполняет настроенную сервером матрицу поиска за последние 24 часа. "
        "Возвращает страницу ещё не классифицированных вакансий и next_cursor; "
        "клиент не управляет запросами, регионами или опытом."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def search_vacancies(
    cursor: Annotated[str | None, Field(max_length=500)] = None,
) -> SearchResponse:
    try:
        async with create_http_client() as http_client:
            return await search_new_vacancies(
                VacancyService(HHClient(http_client)),
                required_env("DATABASE_URL"),
                now=datetime.now(UTC),
                cursor=cursor,
            )
    except RelayError as error:
        _raise_tool_error(error)


@mcp.tool(
    name="get_vacancy",
    title="Полная карточка вакансии hh.ru",
    description=(
        "Получает полное HTML-описание и детали вакансии по ID из результатов поиска."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_vacancy(vacancy_id: int) -> VacancyDetail:
    try:
        async with create_http_client() as http_client:
            return await VacancyService(HHClient(http_client)).get_vacancy(vacancy_id)
    except RelayError as error:
        _raise_tool_error(error)


@mcp.tool(
    name="save_classified_vacancies",
    title="Сохранить классифицированные вакансии",
    description=(
        "Сохраняет до 15 обработанных свежих вакансий; classification — "
        "S/A/B/C/rejected. Перед сохранением повторно загружает канонические "
        "карточки из hh.ru."
    ),
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def save_classified_vacancies(
    vacancies: Annotated[list[ClassifiedVacancy], Field(min_length=1, max_length=15)],
) -> SaveClassifiedVacanciesResult:
    async with create_http_client() as http_client:
        service = VacancyService(HHClient(http_client))
        return await save_classifications(
            service,
            required_env("DATABASE_URL"),
            vacancies,
        )


mcp_http_app = mcp.streamable_http_app()


def _raise_tool_error(error: RelayError) -> NoReturn:
    message = f"{error.code}: {error.message}"
    raise ToolError(message) from error
