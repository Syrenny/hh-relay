import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
from psycopg.rows import dict_row

VACANCY_STATUSES: Final = frozenset(
    {"new", "interesting", "applied", "not_suitable", "archived"}
)


async def insert_vacancy(database_url: str, detail: dict[str, Any]) -> bool:
    salary = detail.get("salary")
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        result = await connection.execute(
            """
            INSERT INTO vacancies (
                id, name, employer, url, salary, area, published_at, detail
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                str(detail["id"]),
                detail["name"],
                (detail.get("employer") or {}).get("name"),
                detail["url"],
                json.dumps(salary) if salary is not None else None,
                (detail.get("area") or {}).get("name"),
                detail["published_at"],
                json.dumps(detail),
            ),
        )
        return result.rowcount == 1


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


async def pending_vacancies(database_url: str, limit: int = 15) -> list[dict[str, Any]]:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            """
            SELECT id, detail FROM vacancies
            WHERE evaluated_at IS NULL
            ORDER BY published_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) async for row in result]


async def save_evaluations(
    database_url: str,
    evaluations: Sequence[dict[str, Any]],
) -> None:
    now = datetime.now(UTC)
    async with (
        await psycopg.AsyncConnection.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        for evaluation in evaluations:
            await cursor.execute(
                """
                    UPDATE vacancies SET
                        rating = %s, rationale = %s, requirements = %s,
                        warnings = %s, evaluated_at = %s, updated_at = %s
                    WHERE id = %s AND evaluated_at IS NULL
                    """,
                (
                    evaluation["rating"],
                    evaluation["rationale"],
                    json.dumps(evaluation["requirements"]),
                    json.dumps(evaluation["warnings"]),
                    now,
                    now,
                    evaluation["vacancy_id"],
                ),
            )


async def unemailed_matches(database_url: str) -> list[dict[str, Any]]:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            """
            SELECT * FROM vacancies
            WHERE rating IN ('strong', 'debatable')
              AND user_status IN ('new', 'interesting')
              AND emailed_at IS NULL
            ORDER BY published_at DESC
            """
        )
        return [dict(row) async for row in result]


async def mark_emailed(database_url: str, ids: Sequence[str]) -> None:
    if not ids:
        return
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            UPDATE vacancies SET emailed_at = now(), updated_at = now()
            WHERE id = ANY(%s)
            """,
            (list(ids),),
        )


async def daily_token_usage(database_url: str) -> int:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS total FROM (
                SELECT input_tokens + output_tokens AS total, started_at AS used_at
                FROM monitor_runs
                UNION ALL
                SELECT input_tokens + output_tokens AS total, created_at AS used_at
                FROM cover_letters
            ) usage WHERE used_at >= date_trunc('day', now())
            """
        )
        row = await result.fetchone()
        return int(row["total"] if row else 0)


async def create_monitor_run(database_url: str) -> int:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            "INSERT INTO monitor_runs DEFAULT VALUES RETURNING id"
        )
        row = await result.fetchone()
        return int(row["id"])


async def finish_monitor_run(  # noqa: PLR0913
    database_url: str,
    run_id: int,
    *,
    status: str,
    found_count: int = 0,
    new_count: int = 0,
    evaluated_count: int = 0,
    emailed_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: str | None = None,
) -> None:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            UPDATE monitor_runs SET
                finished_at = now(), status = %s, found_count = %s,
                new_count = %s, evaluated_count = %s, emailed_count = %s,
                input_tokens = %s, output_tokens = %s, error = %s
            WHERE id = %s
            """,
            (
                status,
                found_count,
                new_count,
                evaluated_count,
                emailed_count,
                input_tokens,
                output_tokens,
                error,
                run_id,
            ),
        )


async def list_vacancies(
    database_url: str, status: str | None = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM vacancies"
    params: tuple[str, ...] = ()
    if status:
        query += " WHERE user_status = %s"
        params = (status,)
    query += " ORDER BY published_at DESC"
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


async def save_cover_letter(  # noqa: PLR0913
    database_url: str,
    vacancy_id: str,
    result: dict[str, Any],
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> None:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            INSERT INTO cover_letters (
                vacancy_id, letter, warning, special_requirement, question, model,
                input_tokens, output_tokens
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                vacancy_id,
                result.get("letter"),
                result.get("warning"),
                result.get("special_requirement"),
                result.get("question"),
                model,
                input_tokens,
                output_tokens,
            ),
        )


async def latest_cover_letter(
    database_url: str, vacancy_id: str
) -> dict[str, Any] | None:
    async with await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    ) as connection:
        result = await connection.execute(
            """
            SELECT * FROM cover_letters WHERE vacancy_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (vacancy_id,),
        )
        row = await result.fetchone()
        return dict(row) if row else None
