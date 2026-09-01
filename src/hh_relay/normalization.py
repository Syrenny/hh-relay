from pydantic import ValidationError

from hh_relay.errors import UpstreamStructureError
from hh_relay.models import (
    Address,
    Area,
    Employer,
    HHReference,
    HHSalary,
    HHVacancy,
    HHVacancyDetail,
    Salary,
    Snippet,
    Vacancy,
    VacancyDetail,
)


def normalize_vacancy(vacancy: HHVacancy) -> Vacancy:
    try:
        return Vacancy(
            id=vacancy.id,
            name=vacancy.name,
            url=vacancy.alternate_url,
            employer=(
                Employer(id=vacancy.employer.id, name=vacancy.employer.name)
                if vacancy.employer
                else None
            ),
            area=(
                Area(id=vacancy.area.id, name=vacancy.area.name)
                if vacancy.area
                else None
            ),
            salary=_normalize_salary(vacancy.salary_range or vacancy.salary),
            experience=vacancy.experience.id if vacancy.experience else None,
            published_at=vacancy.published_at,
            creation_time=None,
            snippet=(
                Snippet(
                    requirement=vacancy.snippet.requirement,
                    responsibility=vacancy.snippet.responsibility,
                )
                if vacancy.snippet
                else None
            ),
        )
    except ValidationError as error:
        raise UpstreamStructureError from error


def normalize_vacancy_detail(vacancy: HHVacancyDetail) -> VacancyDetail:
    summary = normalize_vacancy(vacancy)
    try:
        return VacancyDetail(
            **summary.model_dump(exclude={"snippet"}),
            snippet=summary.snippet,
            description=vacancy.description,
            valid_through=vacancy.expires_at,
            key_skills=[skill.name for skill in vacancy.key_skills],
            address=(
                Address(
                    display_name=vacancy.address.raw,
                    city=vacancy.address.city,
                    street=vacancy.address.street,
                )
                if vacancy.address
                else None
            ),
            employment_form=_reference_id(vacancy.employment_form),
            work_formats=_reference_ids(vacancy.work_format),
            work_schedule_by_days=_reference_ids(vacancy.work_schedule_by_days),
            working_hours=_reference_ids(vacancy.working_hours),
        )
    except ValidationError as error:
        raise UpstreamStructureError from error


def _normalize_salary(salary: HHSalary | None) -> Salary | None:
    if salary is None:
        return None
    return Salary(
        from_=salary.from_,
        to=salary.to,
        currency=salary.currency,
        gross=salary.gross,
        mode=_reference_id(salary.mode),
        frequency=_reference_id(salary.frequency),
    )


def _reference_id(reference: HHReference | None) -> str | None:
    if reference is None:
        return None
    return reference.id or reference.name


def _reference_ids(references: list[HHReference]) -> list[str]:
    return [value for item in references if (value := _reference_id(item))]
