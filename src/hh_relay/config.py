import os
from dataclasses import dataclass
from typing import Final

DEFAULT_OPENAI_MODEL: Final = "gpt-5.4-mini"
DEFAULT_DAILY_TOKEN_BUDGET: Final = 250_000


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"{name} is not configured"
        raise RuntimeError(msg)
    return value


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    database_url: str
    openai_api_key: str
    openai_model: str
    daily_token_budget: int
    relay_base_url: str
    resend_api_key: str | None
    email_from: str | None
    email_to: str | None
    dashboard_base_url: str

    @classmethod
    def from_env(cls) -> "MonitorSettings":
        return cls(
            database_url=required_env("DATABASE_URL"),
            openai_api_key=required_env("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
            daily_token_budget=int(
                os.getenv("OPENAI_DAILY_TOKEN_BUDGET")
                or str(DEFAULT_DAILY_TOKEN_BUDGET)
            ),
            relay_base_url=(
                os.getenv("HH_RELAY_BASE_URL") or "https://hh-relay.vercel.app"
            ).rstrip("/"),
            resend_api_key=os.getenv("RESEND_API_KEY"),
            email_from=os.getenv("EMAIL_FROM"),
            email_to=os.getenv("EMAIL_TO"),
            dashboard_base_url=(
                os.getenv("DASHBOARD_BASE_URL")
                or "https://hh-relay.vercel.app/dashboard"
            ).rstrip("/"),
        )
