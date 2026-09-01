import json
from pathlib import Path

from hh_relay.models import HHVacancy, HHVacancyDetail
from hh_relay.normalization import normalize_vacancy, normalize_vacancy_detail

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalizes_confirmed_search_fields() -> None:
    payload = json.loads((FIXTURES / "search.json").read_text())["items"][0]
    vacancy = normalize_vacancy(HHVacancy.model_validate(payload))

    assert vacancy.id == "101"
    assert vacancy.name == "Python & FastAPI Developer"
    assert str(vacancy.url) == "https://hh.ru/vacancy/101"
    assert vacancy.employer is not None
    assert vacancy.employer.model_dump() == {"id": "501", "name": "Example Employer"}
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
    assert vacancy.creation_time is None
    assert vacancy.snippet is not None
    assert vacancy.snippet.requirement == "Python & SQL"


def test_normalizes_confirmed_detail_fields() -> None:
    payload = json.loads((FIXTURES / "vacancy.json").read_text())
    vacancy = normalize_vacancy_detail(HHVacancyDetail.model_validate(payload))

    assert vacancy.description == "<p>Full &amp; detailed description</p>"
    assert vacancy.key_skills == ["Python", "FastAPI"]
    assert vacancy.address is not None
    assert vacancy.address.display_name == "Москва, Тверская улица"
    assert vacancy.employment_form == "FULL"
    assert vacancy.work_formats == ["REMOTE"]
    assert vacancy.work_schedule_by_days == ["FIVE_ON_TWO_OFF"]
    assert vacancy.working_hours == ["HOURS_8"]
