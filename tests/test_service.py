from datetime import UTC, datetime

import pytest

from hh_relay.models import Experience, HHSearchResponse
from hh_relay.service import MAX_SEARCH_PAGES, MAX_SEARCH_RESULTS, VacancyService

NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


def make_page(
    publications: list[tuple[int, str] | tuple[int, str, bool]],
    *,
    has_next: bool,
) -> HHSearchResponse:
    return HHSearchResponse.model_validate(
        {
            "items": [
                {
                    "id": str(vacancy_id),
                    "name": f"Vacancy {vacancy_id}",
                    "alternate_url": f"https://hh.ru/vacancy/{vacancy_id}",
                    "published_at": item[1],
                }
                for item in publications
                for vacancy_id in [item[0]]
            ],
            "page": 0,
            "pages": 2 if has_next else 1,
            "per_page": 100,
            "found": len(publications),
        }
    )


class FakeClient:
    def __init__(self, pages: list[HHSearchResponse]) -> None:
        self.pages = pages
        self.calls: list[int] = []

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
        del text, area, experience, per_page, date_from, date_to
        self.calls.append(page)
        result = self.pages[page]
        result.page = page
        if result.pages > 1:
            result.pages = len(self.pages)
        return result


@pytest.mark.asyncio
async def test_search_fetches_until_cutoff_and_deduplicates() -> None:
    client = FakeClient(
        [
            make_page(
                [
                    (1, "2026-08-25T13:00:00+00:00"),
                    (2, "2026-08-24T14:00:00+00:00"),
                ],
                has_next=True,
            ),
            make_page(
                [
                    (2, "2026-08-24T14:00:00+00:00"),
                    (3, "2026-08-24T13:59:59+00:00"),
                ],
                has_next=True,
            ),
        ]
    )

    result = await VacancyService(client).search(
        text="Python",
        area=1,
        experience=None,
        now=NOW,
    )

    assert client.calls == [0, 1]
    assert [vacancy.id for vacancy in result.vacancies] == ["1", "2"]
    assert result.pages_fetched == 2
    assert result.cutoff == datetime(2026, 8, 24, 14, tzinfo=UTC)
    assert result.truncated is False


@pytest.mark.asyncio
async def test_search_marks_result_truncated_at_internal_limit() -> None:
    client = FakeClient(
        [
            make_page(
                [(page + 1, "2026-08-25T13:00:00+00:00")],
                has_next=True,
            )
            for page in range(MAX_SEARCH_PAGES + 1)
        ]
    )

    result = await VacancyService(client).search(
        text="Python",
        area=None,
        experience=None,
        now=NOW,
    )

    assert result.pages_fetched == MAX_SEARCH_PAGES
    assert result.truncated is True


@pytest.mark.asyncio
async def test_empty_page_is_natural_end_not_truncation() -> None:
    client = FakeClient(
        [make_page([], has_next=True)],
    )

    result = await VacancyService(client).search(
        text="Python",
        area=None,
        experience=None,
        now=NOW,
    )

    assert result.pages_fetched == 1
    assert result.truncated is False


@pytest.mark.asyncio
async def test_search_limits_result_for_action_payload() -> None:
    client = FakeClient(
        [
            make_page(
                [
                    (vacancy_id, "2026-08-25T13:00:00+00:00")
                    for vacancy_id in range(1, MAX_SEARCH_RESULTS + 2)
                ],
                has_next=False,
            )
        ]
    )

    result = await VacancyService(client).search(
        text="Python",
        area=None,
        experience=None,
        now=NOW,
    )

    assert result.count == MAX_SEARCH_RESULTS
    assert result.truncated is True


@pytest.mark.asyncio
async def test_null_paging_is_natural_single_page_result() -> None:
    page = make_page(
        [(1, "2026-08-25T13:00:00+00:00")],
        has_next=False,
    )
    client = FakeClient([page])

    result = await VacancyService(client).search(
        text="Python",
        area=None,
        experience=None,
        now=NOW,
    )

    assert result.count == 1
    assert result.pages_fetched == 1
    assert result.truncated is False
