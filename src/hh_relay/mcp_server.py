from datetime import UTC, datetime
from typing import NoReturn

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from hh_relay.client import HHClient, create_http_client
from hh_relay.errors import RelayError
from hh_relay.models import Experience, SearchResponse, VacancyDetail
from hh_relay.service import VacancyService

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

mcp = FastMCP(
    name="hh.ru Vacancy Relay",
    instructions=(
        "Сначала ищите компактный список вакансий через search_vacancies. "
        "Вызывайте get_vacancy только для выбранных ID, когда нужно полное описание."
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
        "Ищет вакансии за последние 24 часа. Возвращает компактный список без "
        "snippet и полного описания."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def search_vacancies(
    text: str,
    area: int | None = None,
    experience: Experience | None = None,
) -> SearchResponse:
    try:
        async with create_http_client() as http_client:
            return await VacancyService(HHClient(http_client)).search(
                text=text,
                area=area,
                experience=experience,
                now=datetime.now(UTC),
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


mcp_http_app = mcp.streamable_http_app()


def _raise_tool_error(error: RelayError) -> NoReturn:
    message = f"{error.code}: {error.message}"
    raise ToolError(message) from error
