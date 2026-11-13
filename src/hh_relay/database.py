import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
from psycopg.rows import dict_row

from hh_relay.models import SearchSettings
from hh_relay.service import DEFAULT_SEARCH_SETTINGS

VACANCY_STATUSES: Final = frozenset({"new", "archived"})


async def get_search_settings(database_url: str) -> SearchSettings:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            "SELECT queries, experiences FROM search_settings WHERE id = 1"
        )
        row = await result.fetchone()
    if row is None:
        return DEFAULT_SEARCH_SETTINGS.model_copy(deep=True)
    return SearchSettings.model_validate(row)


async def save_search_settings(database_url: str, settings: SearchSettings) -> None:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            INSERT INTO search_settings (id, queries, experiences)
            VALUES (1, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                queries = EXCLUDED.queries,
                experiences = EXCLUDED.experiences,
                updated_at = now()
            """,
            (
                json.dumps(settings.queries),
                [item.value for item in settings.experiences],
            ),
        )


async def known_vacancy_ids(database_url: str, ids: Sequence[str]) -> set[str]:
    if not ids:
        return set()
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            "SELECT id FROM vacancies WHERE id = ANY(%s)", (list(ids),)
        )
        return {row["id"] async for row in result}


async def save_classified_vacancy(  # noqa: PLR0913
    database_url: str,
    detail: dict[str, Any],
    *,
    tier: str,
    rationale: str,
    requirements: Sequence[str],
    warnings: Sequence[str],
) -> str:
    salary = detail.get("salary")
    values = (
        str(detail["id"]),
        detail["name"],
        (detail.get("employer") or {}).get("name"),
        detail["url"],
        json.dumps(salary) if salary is not None else None,
        (detail.get("area") or {}).get("name"),
        detail["published_at"],
        json.dumps(detail),
        tier,
        rationale,
        json.dumps(list(requirements)),
        json.dumps(list(warnings)),
        datetime.now(UTC),
    )
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            """
            INSERT INTO vacancies (
                id, name, employer, url, salary, area, published_at, detail,
                tier, rationale, requirements, warnings, evaluated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                employer = EXCLUDED.employer,
                url = EXCLUDED.url,
                salary = EXCLUDED.salary,
                area = EXCLUDED.area,
                published_at = EXCLUDED.published_at,
                detail = EXCLUDED.detail,
                tier = EXCLUDED.tier,
                rationale = EXCLUDED.rationale,
                requirements = EXCLUDED.requirements,
                warnings = EXCLUDED.warnings,
                evaluated_at = EXCLUDED.evaluated_at,
                updated_at = now()
            WHERE (
                vacancies.name,
                vacancies.employer,
                vacancies.url,
                vacancies.salary,
                vacancies.area,
                vacancies.published_at,
                vacancies.detail,
                vacancies.tier,
                vacancies.rationale,
                vacancies.requirements,
                vacancies.warnings
            ) IS DISTINCT FROM (
                EXCLUDED.name,
                EXCLUDED.employer,
                EXCLUDED.url,
                EXCLUDED.salary,
                EXCLUDED.area,
                EXCLUDED.published_at,
                EXCLUDED.detail,
                EXCLUDED.tier,
                EXCLUDED.rationale,
                EXCLUDED.requirements,
                EXCLUDED.warnings
            )
            RETURNING (xmax = 0) AS inserted
            """,
            values,
        )
        row = await result.fetchone()
        if row is None:
            return "unchanged"
        return "created" if row["inserted"] else "updated"


async def list_vacancies(
    database_url: str, status: str | None = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM vacancies"
    params: tuple[str, ...] = ()
    if status:
        query += " WHERE user_status = %s"
        params = (status,)
    query += """
        ORDER BY CASE tier
            WHEN 'S' THEN 1
            WHEN 'A' THEN 2
            WHEN 'B' THEN 3
            WHEN 'C' THEN 4
            ELSE 5
        END, published_at DESC
    """
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(query, params)
        return [dict(row) async for row in result]


async def get_vacancy(database_url: str, vacancy_id: str) -> dict[str, Any] | None:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            "SELECT * FROM vacancies WHERE id = %s", (vacancy_id,)
        )
        row = await result.fetchone()
        return dict(row) if row else None


async def update_vacancy_status(
    database_url: str, vacancy_id: str, status: str
) -> bool:
    if status not in VACANCY_STATUSES:
        return False
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        result = await connection.execute(
            "UPDATE vacancies SET user_status = %s, updated_at = now() WHERE id = %s",
            (status, vacancy_id),
        )
        return result.rowcount == 1


async def archive_visible_vacancies(database_url: str) -> int:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        result = await connection.execute(
            """
            UPDATE vacancies
            SET user_status = 'archived', updated_at = now()
            WHERE user_status = 'new' AND tier IN ('S', 'A', 'B', 'C')
            """
        )
        return result.rowcount
