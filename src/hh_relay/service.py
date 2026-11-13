import asyncio
import base64
import binascii
import json
from datetime import UTC, datetime, timedelta
from typing import Final

from hh_relay.client import HHClient
from hh_relay.errors import InvalidCursorError
from hh_relay.models import (
    Experience,
    SearchResponse,
    SearchSettings,
    Vacancy,
    VacancyDetail,
)
from hh_relay.normalization import normalize_vacancy, normalize_vacancy_detail

SEARCH_WINDOW: Final = timedelta(hours=24)
SEARCH_PAGE_SIZE: Final = 100
RESULT_PAGE_SIZE: Final = 30
SEARCH_CONCURRENCY: Final = 4
DEFAULT_SEARCH_SETTINGS: Final = SearchSettings(
    queries=[
        "Python backend",
        "Backend Python",
        "Python developer",
        "Python разработчик",
        "Junior Python",
        "Django developer",
        "FastAPI",
    ],
    experiences=[Experience.NO_EXPERIENCE, Experience.BETWEEN_ONE_AND_THREE],
)


class VacancyService:
    def __init__(self, client: HHClient) -> None:
        self._client = client

    async def search(
        self,
        *,
        settings: SearchSettings,
        now: datetime,
    ) -> SearchResponse:
        current_time = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        cutoff = current_time - SEARCH_WINDOW
        vacancies: list[Vacancy] = []
        seen_ids: set[str] = set()
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)
        searches = [
            self._search_query(
                text=text,
                experience=experience,
                cutoff=cutoff,
                current_time=current_time,
                semaphore=semaphore,
            )
            for text in settings.queries
            for experience in settings.experiences
        ]
        results = await asyncio.gather(*searches)
        pages_fetched = sum(pages for _, pages in results)
        for found, _ in results:
            for vacancy in found:
                if vacancy.id in seen_ids:
                    continue
                seen_ids.add(vacancy.id)
                vacancies.append(vacancy)

        vacancies.sort(
            key=lambda vacancy: (_aware(vacancy.published_at), vacancy.id),
            reverse=True,
        )
        return SearchResponse(
            count=len(vacancies),
            total_count=len(vacancies),
            vacancies=vacancies,
            queries_executed=len(settings.queries) * len(settings.experiences),
            pages_fetched=pages_fetched,
            cutoff=cutoff,
        )

    async def _search_query(
        self,
        *,
        text: str,
        experience: Experience,
        cutoff: datetime,
        current_time: datetime,
        semaphore: asyncio.Semaphore,
    ) -> tuple[list[Vacancy], int]:
        vacancies: list[Vacancy] = []
        pages_fetched = 0
        page_number = 0
        async with semaphore:
            while True:
                page = await self._client.search_page(
                    text=text,
                    area=None,
                    experience=experience,
                    page=page_number,
                    per_page=SEARCH_PAGE_SIZE,
                    date_from=cutoff,
                    date_to=current_time,
                )
                pages_fetched += 1
                normalized = [normalize_vacancy(item) for item in page.items]
                vacancies.extend(
                    vacancy
                    for vacancy in normalized
                    if _aware(vacancy.published_at) >= cutoff
                )
                if not normalized or page.page + 1 >= page.pages:
                    break
                page_number += 1
        return vacancies, pages_fetched

    async def get_vacancy(self, vacancy_id: int) -> VacancyDetail:
        vacancy = await self._client.get_vacancy(vacancy_id)
        return normalize_vacancy_detail(vacancy)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def paginate_search_response(
    response: SearchResponse,
    cursor: str | None,
) -> SearchResponse:
    start = 0
    if cursor is not None:
        cursor_key = _decode_cursor(cursor)
        for index, vacancy in enumerate(response.vacancies):
            key = _cursor_key(vacancy.published_at, vacancy.id)
            if key < cursor_key:
                start = index
                break
        else:
            start = len(response.vacancies)

    page = response.vacancies[start : start + RESULT_PAGE_SIZE]
    has_next = start + RESULT_PAGE_SIZE < len(response.vacancies)
    next_cursor = None
    if has_next and page:
        last = page[-1]
        next_cursor = _encode_cursor(_aware(last.published_at), last.id)
    return response.model_copy(
        update={
            "count": len(page),
            "total_count": len(response.vacancies),
            "vacancies": page,
            "next_cursor": next_cursor,
        }
    )


def _encode_cursor(published_at: datetime, vacancy_id: str) -> str:
    payload = json.dumps(
        _cursor_key(published_at, vacancy_id),
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        raise InvalidCursorError from None
    if not isinstance(payload, list) or not all(
        isinstance(item, str) for item in payload
    ):
        raise InvalidCursorError
    try:
        published_at, vacancy_id = payload
        parsed = datetime.fromisoformat(published_at)
    except (ValueError, TypeError):
        raise InvalidCursorError from None
    return _cursor_key(parsed, vacancy_id)


def _cursor_key(published_at: datetime, vacancy_id: str) -> tuple[str, str]:
    return _aware(published_at).astimezone(UTC).isoformat(), vacancy_id
