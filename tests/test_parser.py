from datetime import UTC, datetime
from pathlib import Path

import pytest

from hh_relay.errors import UpstreamStructureError
from hh_relay.parser import extract_vacancies, filter_recent_unique, normalize_vacancy

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
    assert vacancy.published_at == datetime(2026, 8, 25, 13, tzinfo=UTC)
    assert vacancy.snippet is not None
    assert vacancy.snippet.requirement == "Python & SQL"
    assert vacancy.snippet.responsibility == "Backend development"


def test_filter_recent_and_deduplicate_by_vacancy_id() -> None:
    normalized = [
        normalize_vacancy(item) for item in extract_vacancies(FIXTURE_PATH.read_text())
    ]

    result = filter_recent_unique(
        normalized,
        hours=24,
        now=datetime(2026, 8, 25, 14, tzinfo=UTC),
    )

    assert [vacancy.id for vacancy in result] == ["101"]


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
