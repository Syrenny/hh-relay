import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from hh_relay.ai_service import CoverLetterResult, generate_cover_letter
from hh_relay.config import (
    DEFAULT_DAILY_TOKEN_BUDGET,
    DEFAULT_OPENAI_MODEL,
    required_env,
)
from hh_relay.database import (
    VACANCY_STATUSES,
    daily_token_usage,
    get_vacancy,
    latest_cover_letter,
    list_vacancies,
    save_cover_letter,
    update_vacancy_status,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
security = HTTPBasic()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

STATUS_LABELS = {
    "new": "Новые",
    "interesting": "Интересные",
    "applied": "Откликнулся",
    "not_suitable": "Не подходят",
    "archived": "Архив",
}
RATING_LABELS = {
    "strong": "Сильное совпадение",
    "debatable": "Спорно",
    "skip": "Не стоит тратить время",
    None: "Ожидает оценки",
}


def _authenticate(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> None:
    username = os.getenv("DASHBOARD_USERNAME", "")
    password = os.getenv("DASHBOARD_PASSWORD", "")
    valid = (
        bool(username and password)
        and secrets.compare_digest(credentials.username.encode(), username.encode())
        and secrets.compare_digest(credentials.password.encode(), password.encode())
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dashboard credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


DashboardAuth = Annotated[None, Depends(_authenticate)]


def _verify_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if origin == expected or (referer and referer.startswith(f"{expected}/")):
        return
    raise HTTPException(status_code=403, detail="Invalid request origin")


def _salary(value: object) -> str:
    if not isinstance(value, dict):
        return "Зарплата не указана"
    start, end, currency = value.get("from"), value.get("to"), value.get("currency")
    if start and end:
        return f"{start}-{end} {currency or ''}".strip()
    if start:
        return f"от {start} {currency or ''}".strip()
    if end:
        return f"до {end} {currency or ''}".strip()
    return "Зарплата не указана"


templates.env.globals.update(
    status_labels=STATUS_LABELS,
    rating_labels=RATING_LABELS,
    salary_text=_salary,
)


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _auth: DashboardAuth,
    vacancy_status: str | None = None,
) -> HTMLResponse:
    if vacancy_status and vacancy_status not in VACANCY_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown vacancy status")
    vacancies = await list_vacancies(required_env("DATABASE_URL"), vacancy_status)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"vacancies": vacancies, "active_status": vacancy_status},
    )


@router.get("/vacancies/{vacancy_id}", response_class=HTMLResponse)
async def vacancy_page(
    request: Request,
    vacancy_id: str,
    _auth: DashboardAuth,
) -> HTMLResponse:
    database_url = required_env("DATABASE_URL")
    vacancy = await get_vacancy(database_url, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    letter = await latest_cover_letter(database_url, vacancy_id)
    return templates.TemplateResponse(
        request=request,
        name="vacancy.html",
        context={"vacancy": vacancy, "letter": letter},
    )


@router.post("/vacancies/{vacancy_id}/status")
async def set_vacancy_status(
    request: Request,
    vacancy_id: str,
    _auth: DashboardAuth,
    vacancy_status: Annotated[str, Form()],
) -> RedirectResponse:
    _verify_origin(request)
    updated = await update_vacancy_status(
        required_env("DATABASE_URL"), vacancy_id, vacancy_status
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Invalid vacancy or status")
    return RedirectResponse(
        request.headers.get("referer", "/dashboard"), status_code=303
    )


@router.post("/vacancies/{vacancy_id}/cover-letter")
async def create_cover_letter(
    request: Request,
    vacancy_id: str,
    _auth: DashboardAuth,
) -> RedirectResponse:
    _verify_origin(request)
    database_url = required_env("DATABASE_URL")
    budget = int(
        os.getenv("OPENAI_DAILY_TOKEN_BUDGET") or str(DEFAULT_DAILY_TOKEN_BUDGET)
    )
    if await daily_token_usage(database_url) >= budget:
        raise HTTPException(status_code=429, detail="Daily OpenAI token budget reached")
    vacancy = await get_vacancy(database_url, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    result = await generate_cover_letter(
        api_key=required_env("OPENAI_API_KEY"),
        model=model,
        vacancy=vacancy["detail"],
    )
    letter = CoverLetterResult.model_validate(result.payload)
    await save_cover_letter(
        database_url,
        vacancy_id,
        letter.model_dump(),
        model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return RedirectResponse(f"/dashboard/vacancies/{vacancy_id}", status_code=303)
