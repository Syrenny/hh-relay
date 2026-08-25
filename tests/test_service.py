from datetime import UTC, datetime

import pytest

from hh_relay.models import Experience, UpstreamSearchResult
from hh_relay.service import MAX_SEARCH_PAGES, VacancyService

NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


def make_page(
    publications: list[tuple[int, str] | tuple[int, str, bool]],
    *,
    has_next: bool,
) -> UpstreamSearchResult:
    return UpstreamSearchResult.model_validate(
        {
            "vacancies": [
                {
                    "vacancyId": vacancy_id,
                    "name": f"Vacancy {vacancy_id}",
                    "links": {"desktop": f"https://hh.ru/vacancy/{vacancy_id}"},
                    "publicationTime": {"$": item[1]},
                    "@isAdv": item[2] if len(item) == 3 else False,
                }
                for item in publications
                for vacancy_id in [item[0]]
            ],
            "paging": {"next": {"page": 1, "disabled": not has_next}},
        }
    )


class FakeClient:
    def __init__(self, pages: list[UpstreamSearchResult]) -> None:
        self.pages = pages
        self.calls: list[int] = []

    async def search_page(
        self,
        *,
        text: str,
        area: int | None,
        experience: Experience | None,
        page: int,
    ) -> UpstreamSearchResult:
        del text, area, experience
        self.calls.append(page)
        return self.pages[page]


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
            for page in range(MAX_SEARCH_PAGES)
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
async def test_old_ad_does_not_stop_pagination() -> None:
    client = FakeClient(
        [
            make_page(
                [(99, "2026-08-20T13:00:00+00:00", True)],
                has_next=True,
            ),
            make_page(
                [(1, "2026-08-25T13:00:00+00:00")],
                has_next=False,
            ),
        ]
    )

    result = await VacancyService(client).search(
        text="Python",
        area=None,
        experience=None,
        now=NOW,
    )

    assert client.calls == [0, 1]
    assert [vacancy.id for vacancy in result.vacancies] == ["1"]
