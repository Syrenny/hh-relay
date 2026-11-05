from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from hh_relay import selection_service
from hh_relay.errors import VacancyNotFoundError
from hh_relay.models import ClassifiedVacancy, VacancyDetail, VacancyTier

NOW = datetime(2026, 11, 6, 8, tzinfo=UTC)


def make_detail(*, published_at: datetime = NOW) -> VacancyDetail:
    return VacancyDetail.model_validate(
        {
            "id": "101",
            "name": "Python Developer",
            "url": "https://hh.ru/vacancy/101",
            "published_at": published_at,
            "description": "Python backend",
            "key_skills": ["Python"],
            "work_formats": ["Удалённо"],
            "work_schedule_by_days": [],
            "working_hours": [],
        }
    )


def make_classification(
    tier: VacancyTier = VacancyTier.S,
) -> ClassifiedVacancy:
    return ClassifiedVacancy(
        vacancy_id=101,
        tier=tier,
        rationale="Реалистичный уровень и подходящий стек",
        requirements=["Python"],
        warnings=[],
    )


@pytest.mark.asyncio
async def test_saves_canonical_fresh_vacancy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.get_vacancy.return_value = make_detail()
    save = AsyncMock(return_value="created")
    monkeypatch.setattr(selection_service, "save_classified_vacancy", save)

    result = await selection_service.save_classified_vacancies(
        service,
        "postgresql://database",
        [make_classification()],
        now=NOW,
    )

    assert result.created == [101]
    saved_detail = save.await_args.args[1]
    assert saved_detail["name"] == "Python Developer"
    assert saved_detail["url"] == "https://hh.ru/vacancy/101"


@pytest.mark.asyncio
async def test_rejects_old_vacancy_without_database_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.get_vacancy.return_value = make_detail(
        published_at=NOW - timedelta(hours=49)
    )
    save = AsyncMock()
    monkeypatch.setattr(selection_service, "save_classified_vacancy", save)

    result = await selection_service.save_classified_vacancies(
        service,
        "postgresql://database",
        [make_classification()],
        now=NOW,
    )

    assert result.failed[0].code == "vacancy_too_old"
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_reports_upstream_failure() -> None:
    service = AsyncMock()
    service.get_vacancy.side_effect = VacancyNotFoundError()

    result = await selection_service.save_classified_vacancies(
        service,
        "postgresql://database",
        [make_classification()],
        now=NOW,
    )

    assert result.failed[0].code == "vacancy_not_found"


@pytest.mark.asyncio
async def test_rejects_duplicate_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.get_vacancy.return_value = make_detail()
    save = AsyncMock(return_value="unchanged")
    monkeypatch.setattr(selection_service, "save_classified_vacancy", save)

    result = await selection_service.save_classified_vacancies(
        service,
        "postgresql://database",
        [make_classification(), make_classification()],
        now=NOW,
    )

    assert result.unchanged == [101]
    assert result.failed[0].code == "duplicate_input"
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_saves_rejected_classification_with_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.get_vacancy.return_value = make_detail()
    save = AsyncMock(return_value="created")
    monkeypatch.setattr(selection_service, "save_classified_vacancy", save)

    classification = make_classification(VacancyTier.REJECTED)
    classification.rationale = "Python не является основным языком вакансии"
    result = await selection_service.save_classified_vacancies(
        service,
        "postgresql://database",
        [classification],
        now=NOW,
    )

    assert result.created == [101]
    assert save.await_args.kwargs["tier"] == "rejected"
    assert save.await_args.kwargs["rationale"] == classification.rationale
