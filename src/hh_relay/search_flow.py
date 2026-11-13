from datetime import datetime

from hh_relay.database import get_search_settings, known_vacancy_ids
from hh_relay.models import SearchResponse
from hh_relay.service import VacancyService, paginate_search_response


async def search_new_vacancies(
    service: VacancyService,
    database_url: str,
    *,
    now: datetime,
    cursor: str | None,
) -> SearchResponse:
    settings = await get_search_settings(database_url)
    response = await service.search(settings=settings, now=now)
    known_ids = await known_vacancy_ids(
        database_url, [item.id for item in response.vacancies]
    )
    response.vacancies = [
        item for item in response.vacancies if item.id not in known_ids
    ]
    response.count = len(response.vacancies)
    response.total_count = len(response.vacancies)
    return paginate_search_response(response, cursor)
