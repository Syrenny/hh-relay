import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from hh_relay.config import required_env
from hh_relay.database import (
    archive_visible_vacancies,
    get_search_settings,
    get_vacancy,
    list_vacancies,
    save_search_settings,
    update_vacancy_status,
)
from hh_relay.models import Experience, SearchSettings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
security = HTTPBasic()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

TIER_LABELS = {
    "S": "Приоритетный отклик",
    "A": "Хорошее совпадение",
    "B": "Есть оговорки",
    "C": "Слабое совпадение",
}
REJECTED_LABEL = "Не подходит"


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
    tier_labels=TIER_LABELS,
    salary_text=_salary,
)


def _settings_response(
    request: Request,
    settings: SearchSettings,
    error: str | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"settings": settings, "error": error},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _auth: DashboardAuth,
    show_hidden: str | None = None,
) -> HTMLResponse:
    database_url = required_env("DATABASE_URL")
    hidden_view = show_hidden == "true"
    vacancies = await list_vacancies(database_url)
    if hidden_view:
        vacancies = [
            vacancy
            for vacancy in vacancies
            if vacancy["tier"] == "rejected"
            or (vacancy["tier"] in TIER_LABELS and vacancy["user_status"] == "archived")
        ]
        visible_tiers = {**TIER_LABELS, "rejected": REJECTED_LABEL}
    else:
        vacancies = [
            vacancy
            for vacancy in vacancies
            if vacancy["tier"] in TIER_LABELS and vacancy["user_status"] == "new"
        ]
        visible_tiers = TIER_LABELS
    tier_groups = [
        (tier, label, [item for item in vacancies if item["tier"] == tier])
        for tier, label in visible_tiers.items()
    ]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "tier_groups": tier_groups,
            "show_hidden": hidden_view,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    _auth: DashboardAuth,
) -> HTMLResponse:
    settings = await get_search_settings(required_env("DATABASE_URL"))
    return _settings_response(request, settings)


@router.post("/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    _auth: DashboardAuth,
    queries: Annotated[str, Form()],
    experiences: Annotated[list[str] | None, Form()] = None,
) -> Response:
    _verify_origin(request)
    try:
        settings = SearchSettings(
            queries=queries.splitlines(),
            experiences=experiences or [],
        )
    except ValidationError:
        fallback = SearchSettings.model_construct(
            queries=queries.splitlines(),
            experiences=[
                item for item in Experience if item.value in (experiences or [])
            ],
        )
        return _settings_response(
            request,
            fallback,
            "Укажите уникальные непустые запросы и выберите хотя бы один опыт.",
            status_code=422,
        )
    await save_search_settings(required_env("DATABASE_URL"), settings)
    return RedirectResponse("/dashboard/settings", status_code=303)


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
    return templates.TemplateResponse(
        request=request,
        name="vacancy.html",
        context={"vacancy": vacancy},
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


@router.post("/vacancies/archive-all")
async def archive_all_vacancies(
    request: Request,
    _auth: DashboardAuth,
) -> RedirectResponse:
    _verify_origin(request)
    await archive_visible_vacancies(required_env("DATABASE_URL"))
    return RedirectResponse("/dashboard", status_code=303)
