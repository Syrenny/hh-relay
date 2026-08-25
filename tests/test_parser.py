from pathlib import Path

import pytest

from hh_relay.errors import UpstreamStructureError
from hh_relay.parser import (
    extract_vacancies,
    extract_vacancy_detail,
    normalize_vacancy,
    normalize_vacancy_detail,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search.html"


def test_extract_and_normalize_confirmed_ssr_fields() -> None:
    upstream = extract_vacancies(FIXTURE_PATH.read_text())

    vacancy = normalize_vacancy(upstream[0])

    assert vacancy.id == "101"
    assert vacancy.name == "Python & FastAPI Developer"
    assert str(vacancy.url) == "https://hh.ru/vacancy/101"
    assert vacancy.employer is not None
    assert vacancy.employer.model_dump() == {
        "id": "501",
        "name": "Example Employer",
    }
    assert vacancy.area is not None
    assert vacancy.area.model_dump() == {"id": "1", "name": "Москва"}
    assert vacancy.salary is not None
    assert vacancy.salary.model_dump(by_alias=True) == {
        "from": 200000,
        "to": 300000,
        "currency": "RUR",
        "gross": False,
        "mode": "MONTH",
        "frequency": "MONTHLY",
    }
    assert vacancy.experience == "between3And6"
    assert vacancy.published_at.isoformat() == "2026-08-25T13:00:00+00:00"
    assert vacancy.snippet is not None
    assert vacancy.snippet.requirement == "Python & SQL"
    assert vacancy.snippet.responsibility == "Backend development"


def test_extract_and_normalize_vacancy_detail() -> None:
    fixture = Path(__file__).parent / "fixtures" / "vacancy.html"

    vacancy = normalize_vacancy_detail(extract_vacancy_detail(fixture.read_text()))

    assert vacancy.id == "101"
    assert vacancy.description == "<p>Full &amp; detailed description</p>"
    assert vacancy.key_skills == ["Python", "FastAPI"]
    assert vacancy.address is not None
    assert vacancy.address.display_name == "Москва, Тверская улица"
    assert vacancy.work_formats == ["REMOTE"]


@pytest.mark.parametrize(
    "html",
    [
        "<html></html>",
        '<template id="HH-Lux-InitialState">not-json</template>',
        '<template id="HH-Lux-InitialState">{}</template>',
    ],
)
def test_extract_rejects_structure_changes(html: str) -> None:
    with pytest.raises(UpstreamStructureError):
        extract_vacancies(html)
