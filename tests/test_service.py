from datetime import UTC, datetime, timedelta

import pytest

from hh_relay.errors import InvalidCursorError
from hh_relay.models import (
    Experience,
    HHSearchResponse,
    SearchResponse,
    SearchSettings,
    VacancySummary,
)
from hh_relay.service import (
    DEFAULT_SEARCH_SETTINGS,
    RESULT_PAGE_SIZE,
    VacancyService,
    paginate_search_response,
)

NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


def make_page(
    publications: list[tuple[int, str]],
    *,
    page: int = 0,
    pages: int = 1,
) -> HHSearchResponse:
    return HHSearchResponse.model_validate(
        {
            "items": [
                {
                    "id": str(vacancy_id),
                    "name": f"Vacancy {vacancy_id}",
                    "alternate_url": f"https://hh.ru/vacancy/{vacancy_id}",
                    "published_at": published_at,
                }
                for vacancy_id, published_at in publications
            ],
            "page": page,
            "pages": pages,
            "per_page": 100,
            "found": len(publications),
        }
    )


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search_page(  # noqa: PLR0913
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        page: int,
        per_page: int,
        date_from: datetime,
        date_to: datetime,
    ) -> HHSearchResponse:
        self.calls.append(
            {
                "text": text,
                "area": area,
                "experience": experience,
                "page": page,
                "per_page": per_page,
                "date_from": date_from,
                "date_to": date_to,
            }
        )
        vacancy_id = 1 if text == "Python" else 2
        return make_page([(vacancy_id, "2026-08-25T13:00:00+00:00")])


@pytest.mark.asyncio
async def test_search_executes_complete_matrix_and_deduplicates() -> None:
    client = FakeClient()
    settings = SearchSettings(
        queries=["Python", "Django"],
        experiences=[Experience.NO_EXPERIENCE, Experience.BETWEEN_ONE_AND_THREE],
    )

    result = await VacancyService(client).search(settings=settings, now=NOW)

    assert len(client.calls) == 4
    assert {(call["text"], call["experience"]) for call in client.calls} == {
        ("Python", Experience.NO_EXPERIENCE),
        ("Python", Experience.BETWEEN_ONE_AND_THREE),
        ("Django", Experience.NO_EXPERIENCE),
        ("Django", Experience.BETWEEN_ONE_AND_THREE),
    }
    assert all(call["area"] is None for call in client.calls)
    assert all(
        call["date_to"] - call["date_from"] == timedelta(hours=24)  # type: ignore[operator]
        for call in client.calls
    )
    assert [vacancy.id for vacancy in result.vacancies] == ["2", "1"]
    assert result.queries_executed == 4


@pytest.mark.asyncio
async def test_search_fetches_every_upstream_page_without_result_limit() -> None:
    class PagedClient(FakeClient):
        async def search_page(self, **kwargs: object) -> HHSearchResponse:
            page = int(kwargs["page"])
            self.calls.append(dict(kwargs))
            start = page * 40
            return make_page(
                [
                    (vacancy_id, "2026-08-25T13:00:00+00:00")
                    for vacancy_id in range(start + 1, start + 41)
                ],
                page=page,
                pages=2,
            )

    client = PagedClient()
    settings = SearchSettings(
        queries=["Python"], experiences=[Experience.NO_EXPERIENCE]
    )

    result = await VacancyService(client).search(settings=settings, now=NOW)

    assert [call["page"] for call in client.calls] == [0, 1]
    assert result.count == 80
    assert result.pages_fetched == 2


def test_cursor_pagination_returns_every_vacancy_once() -> None:
    vacancies = [
        VacancySummary(
            id=str(vacancy_id),
            name=f"Vacancy {vacancy_id}",
            url=f"https://hh.ru/vacancy/{vacancy_id}",
            published_at=NOW - timedelta(minutes=vacancy_id),
        )
        for vacancy_id in range(1, RESULT_PAGE_SIZE + 6)
    ]
    complete = SearchResponse(
        count=len(vacancies),
        total_count=len(vacancies),
        vacancies=vacancies,
        queries_executed=14,
        pages_fetched=14,
        cutoff=NOW - timedelta(hours=24),
    )

    first = paginate_search_response(complete, None)
    second = paginate_search_response(complete, first.next_cursor)

    assert first.count == RESULT_PAGE_SIZE
    assert first.next_cursor is not None
    assert second.count == 5
    assert second.next_cursor is None
    assert {item.id for item in first.vacancies}.isdisjoint(
        item.id for item in second.vacancies
    )


def test_default_matrix_has_fourteen_combinations() -> None:
    assert len(DEFAULT_SEARCH_SETTINGS.queries) == 7
    assert len(DEFAULT_SEARCH_SETTINGS.experiences) == 2


def test_cursor_pagination_rejects_invalid_cursor() -> None:
    complete = SearchResponse(
        count=0,
        total_count=0,
        vacancies=[],
        queries_executed=14,
        pages_fetched=14,
        cutoff=NOW - timedelta(hours=24),
    )

    with pytest.raises(InvalidCursorError):
        paginate_search_response(complete, "not-a-cursor")
