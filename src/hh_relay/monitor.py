import asyncio
import html
import logging
from typing import Any, Final

import httpx
from bs4 import BeautifulSoup

from hh_relay.ai_service import EvaluationBatch, evaluate_vacancies
from hh_relay.config import MonitorSettings
from hh_relay.database import (
    create_monitor_run,
    daily_token_usage,
    finish_monitor_run,
    insert_vacancy,
    known_vacancy_ids,
    mark_emailed,
    pending_vacancies,
    save_evaluations,
    unemailed_matches,
)

logger = logging.getLogger(__name__)
SEARCHES: Final = (
    ("Python backend", "noExperience"),
    ("Python backend", "between1And3"),
    ("Django Python", "between1And3"),
    ("FastAPI Python", "between1And3"),
)
NOISE_TITLES: Final = (
    "frontend",
    "аналитик",
    "тестировщик",
    "data scientist",
    "devops",
    "системный администратор",
    "1с",
)


def _plausible_title(name: str) -> bool:
    lowered = name.casefold()
    return not any(noise in lowered for noise in NOISE_TITLES)


def _plain_detail(detail: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(detail)
    description = str(normalized.get("description") or "")
    normalized["description"] = BeautifulSoup(description, "html.parser").get_text(
        " ", strip=True
    )
    return normalized


async def _search(client: httpx.AsyncClient, settings: MonitorSettings) -> list[dict]:
    async def request(text: str, experience: str, area: int | None = None) -> dict:
        params: dict[str, str | int] = {"text": text, "experience": experience}
        if area is not None:
            params["area"] = area
        response = await client.get(
            f"{settings.relay_base_url}/api/vacancies/search", params=params
        )
        response.raise_for_status()
        return response.json()

    initial = await asyncio.gather(*(request(*query) for query in SEARCHES))
    extra_tasks = []
    for query, result in zip(SEARCHES, initial, strict=True):
        if result.get("truncated"):
            extra_tasks.extend(request(*query, area=area) for area in (4, 1))
    extra = await asyncio.gather(*extra_tasks) if extra_tasks else []
    unique: dict[str, dict] = {}
    for result in [*initial, *extra]:
        for vacancy in result.get("vacancies", []):
            if _plausible_title(vacancy["name"]):
                unique[str(vacancy["id"])] = vacancy
    return list(unique.values())


async def _load_new_details(
    client: httpx.AsyncClient,
    settings: MonitorSettings,
    vacancies: list[dict],
) -> int:
    known = await known_vacancy_ids(
        settings.database_url, [str(item["id"]) for item in vacancies]
    )
    new_items = [item for item in vacancies if str(item["id"]) not in known][:15]

    async def load(vacancy_id: str) -> dict:
        response = await client.get(
            f"{settings.relay_base_url}/api/vacancies/{vacancy_id}"
        )
        response.raise_for_status()
        return response.json()

    details = await asyncio.gather(
        *(load(str(item["id"])) for item in new_items), return_exceptions=True
    )
    inserted = 0
    for detail in details:
        if isinstance(detail, Exception):
            logger.warning("vacancy_detail_failed error_type=%s", type(detail).__name__)
            continue
        inserted += await insert_vacancy(settings.database_url, _plain_detail(detail))
    return inserted


def _salary_text(value: object) -> str:
    if not isinstance(value, dict):
        return "не указана"
    start = value.get("from")
    end = value.get("to")
    currency = value.get("currency") or ""
    if start and end:
        return f"{start}-{end} {currency}"
    if start:
        return f"от {start} {currency}"
    if end:
        return f"до {end} {currency}"
    return "не указана"


async def _send_email(
    client: httpx.AsyncClient,
    settings: MonitorSettings,
    vacancies: list[dict[str, Any]],
) -> bool:
    if not vacancies:
        return True
    if not all((settings.resend_api_key, settings.email_from, settings.email_to)):
        logger.warning("email_not_configured")
        return False
    cards = []
    for vacancy in vacancies:
        dashboard_url = f"{settings.dashboard_base_url}/vacancies/{vacancy['id']}"
        cards.append(
            "<li>"
            f"<strong>{html.escape(vacancy['name'])}</strong> - "
            f"{html.escape(vacancy.get('employer') or 'Компания не указана')}<br>"
            f"{html.escape(_salary_text(vacancy.get('salary')))} · "
            f"{html.escape(vacancy.get('area') or 'Локация не указана')}<br>"
            f"{html.escape(vacancy.get('rationale') or '')}<br>"
            f'<a href="{html.escape(vacancy["url"])}">hh.ru</a> · '
            f'<a href="{html.escape(dashboard_url)}">Открыть в dashboard</a>'
            "</li>"
        )
    response = await client.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": settings.email_from,
            "to": [settings.email_to],
            "subject": f"Новые вакансии Python backend: {len(vacancies)}",
            "html": "<h1>Новые вакансии</h1><ul>" + "".join(cards) + "</ul>",
        },
    )
    response.raise_for_status()
    return True


async def run_monitor(settings: MonitorSettings) -> None:
    run_id = await create_monitor_run(settings.database_url)
    found = new = evaluated = emailed = input_tokens = output_tokens = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            vacancies = await _search(client, settings)
            found = len(vacancies)
            new = await _load_new_details(client, settings, vacancies)
            pending = await pending_vacancies(settings.database_url)
            used = await daily_token_usage(settings.database_url)
            if pending and used < settings.daily_token_budget:
                result = await evaluate_vacancies(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    vacancies=[item["detail"] for item in pending],
                )
                batch = EvaluationBatch.model_validate(result.payload)
                evaluations = [item.model_dump() for item in batch.evaluations]
                await save_evaluations(settings.database_url, evaluations)
                evaluated = len(evaluations)
                input_tokens = result.input_tokens
                output_tokens = result.output_tokens
            matches = await unemailed_matches(settings.database_url)
            if matches and await _send_email(client, settings, matches):
                await mark_emailed(
                    settings.database_url, [item["id"] for item in matches]
                )
                emailed = len(matches)
        await finish_monitor_run(
            settings.database_url,
            run_id,
            status="completed",
            found_count=found,
            new_count=new,
            evaluated_count=evaluated,
            emailed_count=emailed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as error:
        await finish_monitor_run(
            settings.database_url,
            run_id,
            status="failed",
            found_count=found,
            new_count=new,
            evaluated_count=evaluated,
            emailed_count=emailed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=type(error).__name__,
        )
        raise
