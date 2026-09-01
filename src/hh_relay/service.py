from datetime import UTC, datetime, timedelta
from typing import Final

from hh_relay.client import HHClient
from hh_relay.models import Experience, SearchResponse, Vacancy, VacancyDetail
from hh_relay.normalization import normalize_vacancy, normalize_vacancy_detail

SEARCH_WINDOW: Final = timedelta(hours=24)
MAX_SEARCH_PAGES: Final = 10
MAX_SEARCH_RESULTS: Final = 50
SEARCH_PAGE_SIZE: Final = 100


class VacancyService:
    def __init__(self, client: HHClient) -> None:
        self._client = client

    async def search(
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        now: datetime,
    ) -> SearchResponse:
        current_time = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        cutoff = current_time - SEARCH_WINDOW
        vacancies: list[Vacancy] = []
        seen_ids: set[str] = set()
        pages_fetched = 0
        has_next_page = False
        reached_end = False
        result_overflow = False

        for page_number in range(MAX_SEARCH_PAGES):
            page = await self._client.search_page(
                text=text,
                area=area,
                experience=experience,
                page=page_number,
                per_page=SEARCH_PAGE_SIZE,
                date_from=cutoff,
                date_to=current_time,
            )
            pages_fetched += 1
            has_next_page = page.page + 1 < page.pages
            normalized = [normalize_vacancy(item) for item in page.items]

            for vacancy in normalized:
                published_at = _aware(vacancy.published_at)
                if published_at < cutoff:
                    continue
                if vacancy.id in seen_ids:
                    continue
                seen_ids.add(vacancy.id)
                if len(vacancies) == MAX_SEARCH_RESULTS:
                    result_overflow = True
                    break
                vacancies.append(vacancy)

            reached_end = not normalized or not has_next_page
            if result_overflow or reached_end:
                break

        pages_truncated = (
            pages_fetched == MAX_SEARCH_PAGES and has_next_page and not reached_end
        )
        return SearchResponse(
            count=len(vacancies),
            vacancies=vacancies,
            pages_fetched=pages_fetched,
            truncated=result_overflow or pages_truncated or has_next_page,
            cutoff=cutoff,
        )

    async def get_vacancy(self, vacancy_id: int) -> VacancyDetail:
        vacancy = await self._client.get_vacancy(vacancy_id)
        return normalize_vacancy_detail(vacancy)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
