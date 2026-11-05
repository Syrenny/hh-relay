import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

from hh_relay.database import save_classified_vacancy
from hh_relay.errors import RelayError
from hh_relay.models import (
    ClassifiedVacancy,
    SaveClassifiedVacanciesResult,
    SaveFailure,
)
from hh_relay.service import VacancyService

MAX_VACANCY_AGE: Final = timedelta(hours=48)
MAX_FUTURE_SKEW: Final = timedelta(minutes=5)


async def save_classified_vacancies(
    vacancy_service: VacancyService,
    database_url: str,
    classifications: list[ClassifiedVacancy],
    *,
    now: datetime | None = None,
) -> SaveClassifiedVacanciesResult:
    current_time = now or datetime.now(UTC)
    result = SaveClassifiedVacanciesResult()
    seen_ids: set[int] = set()
    unique_classifications: list[ClassifiedVacancy] = []

    for classification in classifications:
        vacancy_id = classification.vacancy_id
        if vacancy_id in seen_ids:
            result.failed.append(
                SaveFailure(vacancy_id=vacancy_id, code="duplicate_input")
            )
            continue
        seen_ids.add(vacancy_id)
        unique_classifications.append(classification)

    details = await asyncio.gather(
        *(
            vacancy_service.get_vacancy(item.vacancy_id)
            for item in unique_classifications
        ),
        return_exceptions=True,
    )

    for classification, detail in zip(unique_classifications, details, strict=True):
        vacancy_id = classification.vacancy_id
        if isinstance(detail, RelayError):
            error = detail
            result.failed.append(SaveFailure(vacancy_id=vacancy_id, code=error.code))
            continue
        if isinstance(detail, BaseException):
            raise detail

        published_at = detail.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        if published_at < current_time - MAX_VACANCY_AGE:
            result.failed.append(
                SaveFailure(vacancy_id=vacancy_id, code="vacancy_too_old")
            )
            continue
        if published_at > current_time + MAX_FUTURE_SKEW:
            result.failed.append(
                SaveFailure(vacancy_id=vacancy_id, code="invalid_published_at")
            )
            continue

        outcome = await save_classified_vacancy(
            database_url,
            detail.model_dump(mode="json", by_alias=True),
            tier=classification.tier.value,
            rationale=classification.rationale,
            requirements=classification.requirements,
            warnings=classification.warnings,
        )
        getattr(result, outcome).append(vacancy_id)

    return result
