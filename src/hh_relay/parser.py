import json
from html import unescape
from html.parser import HTMLParser

from pydantic import ValidationError

from hh_relay.errors import UpstreamStructureError
from hh_relay.models import (
    Address,
    Area,
    Employer,
    Salary,
    Snippet,
    UpstreamInitialState,
    UpstreamVacancy,
    UpstreamVacancyDetail,
    UpstreamVacancyDetailState,
    Vacancy,
    VacancyDetail,
)

INITIAL_STATE_TEMPLATE_ID = "HH-Lux-InitialState"


class InitialStateTemplateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._inside_target = False
        self._parts: list[str] = []

    @property
    def content(self) -> str | None:
        if not self._parts:
            return None
        return "".join(self._parts)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "template" and dict(attrs).get("id") == INITIAL_STATE_TEMPLATE_ID:
            self._inside_target = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self._inside_target:
            self._inside_target = False

    def handle_data(self, data: str) -> None:
        if self._inside_target:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._inside_target:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._inside_target:
            self._parts.append(f"&#{name};")


def extract_initial_state(html: str) -> object:
    parser = InitialStateTemplateParser()
    parser.feed(html)
    raw_state = parser.content
    if raw_state is None:
        raise UpstreamStructureError

    try:
        return json.loads(unescape(raw_state))
    except (json.JSONDecodeError, TypeError) as error:
        raise UpstreamStructureError from error


def extract_search_result(html: str) -> UpstreamInitialState:
    try:
        return UpstreamInitialState.model_validate(extract_initial_state(html))
    except ValidationError as error:
        raise UpstreamStructureError from error


def extract_vacancies(html: str) -> list[UpstreamVacancy]:
    return extract_search_result(html).vacancy_search_result.vacancies


def extract_vacancy_detail(html: str) -> UpstreamVacancyDetail:
    try:
        state = UpstreamVacancyDetailState.model_validate(extract_initial_state(html))
    except ValidationError as error:
        raise UpstreamStructureError from error
    return state.vacancy_view


def normalize_vacancy(vacancy: UpstreamVacancy) -> Vacancy:
    url = vacancy.links.desktop or vacancy.view_url or vacancy.links.mobile
    if url is None:
        raise UpstreamStructureError

    employer = None
    if vacancy.company is not None:
        employer_name = vacancy.company.visible_name or vacancy.company.name
        if employer_name is not None:
            employer = Employer(
                id=_stringify(vacancy.company.id),
                name=employer_name,
            )

    area = None
    if vacancy.area is not None:
        area = Area(id=_stringify(vacancy.area.id), name=vacancy.area.name)

    salary = None
    if vacancy.compensation is not None:
        salary = Salary(
            from_=vacancy.compensation.from_,
            to=vacancy.compensation.to,
            currency=vacancy.compensation.currency_code,
            gross=vacancy.compensation.gross,
            mode=vacancy.compensation.mode,
            frequency=vacancy.compensation.frequency,
        )

    snippet = None
    if vacancy.snippet is not None:
        snippet = Snippet(
            requirement=vacancy.snippet.req,
            responsibility=vacancy.snippet.resp,
            conditions=vacancy.snippet.cond,
            skills=vacancy.snippet.skill,
            description=vacancy.snippet.desc,
        )

    try:
        return Vacancy(
            id=str(vacancy.vacancy_id),
            name=vacancy.name,
            url=url,
            employer=employer,
            area=area,
            salary=salary,
            experience=vacancy.work_experience,
            published_at=vacancy.publication_time.value,
            creation_time=vacancy.creation_time,
            snippet=snippet,
        )
    except ValidationError as error:
        raise UpstreamStructureError from error


def normalize_vacancy_detail(vacancy: UpstreamVacancyDetail) -> VacancyDetail:
    employer = None
    if vacancy.company is not None:
        employer_name = vacancy.company.visible_name or vacancy.company.name
        if employer_name is not None:
            employer = Employer(
                id=_stringify(vacancy.company.id),
                name=employer_name,
            )

    area = None
    if vacancy.area is not None:
        area = Area(id=_stringify(vacancy.area.id), name=vacancy.area.name)

    salary = None
    if vacancy.compensation is not None:
        salary = Salary(
            from_=vacancy.compensation.from_,
            to=vacancy.compensation.to,
            currency=vacancy.compensation.currency_code,
            gross=vacancy.compensation.gross,
            mode=vacancy.compensation.mode,
            frequency=vacancy.compensation.frequency,
        )

    address = None
    if vacancy.address is not None:
        address = Address(
            display_name=vacancy.address.display_name,
            city=vacancy.address.city,
            street=vacancy.address.street,
        )

    try:
        return VacancyDetail(
            id=str(vacancy.vacancy_id),
            name=vacancy.name,
            url=f"https://hh.ru/vacancy/{vacancy.vacancy_id}",
            employer=employer,
            area=area,
            salary=salary,
            experience=vacancy.work_experience,
            published_at=vacancy.publication_date,
            creation_time=None,
            snippet=None,
            description=vacancy.description,
            valid_through=vacancy.valid_through_time,
            key_skills=(vacancy.key_skills.key_skill if vacancy.key_skills else []),
            address=address,
            employment_form=vacancy.employment_form,
            work_formats=vacancy.work_formats,
            work_schedule_by_days=vacancy.work_schedule_by_days,
            working_hours=vacancy.working_hours,
        )
    except ValidationError as error:
        raise UpstreamStructureError from error


def _stringify(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value)
