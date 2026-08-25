import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser

from pydantic import ValidationError

from hh_relay.errors import UpstreamStructureError
from hh_relay.models import (
    Area,
    Employer,
    Salary,
    Snippet,
    UpstreamInitialState,
    UpstreamVacancy,
    Vacancy,
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


def extract_vacancies(html: str) -> list[UpstreamVacancy]:
    parser = InitialStateTemplateParser()
    parser.feed(html)
    raw_state = parser.content
    if raw_state is None:
        raise UpstreamStructureError

    try:
        decoded = json.loads(unescape(raw_state))
        state = UpstreamInitialState.model_validate(decoded)
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise UpstreamStructureError from error

    return state.vacancy_search_result.vacancies


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


def filter_recent_unique(
    vacancies: Iterable[Vacancy],
    *,
    hours: int,
    now: datetime | None = None,
) -> list[Vacancy]:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    threshold = current_time - timedelta(hours=hours)

    result: list[Vacancy] = []
    seen_ids: set[str] = set()
    for vacancy in vacancies:
        published_at = vacancy.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        if vacancy.id in seen_ids or published_at < threshold:
            continue
        seen_ids.add(vacancy.id)
        result.append(vacancy)
    return result


def _stringify(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value)
