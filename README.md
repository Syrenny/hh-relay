# hh-relay

FastAPI relay для Custom GPT Action и MCP, который ищет вакансии через официальный `api.hh.ru`. Публичные клиенты relay не проходят авторизацию: сервер использует заранее выпущенный application token из защищённой переменной окружения.

## Требования и настройка

- Python 3.13;
- [`uv`](https://docs.astral.sh/uv/);
- одобренное приложение hh.ru и его актуальный application token.

Application token отображается владельцу приложения на `https://dev.hh.ru/admin`. Его нужно выпустить один раз и задать только в окружении сервера:

```bash
export HH_ACCESS_TOKEN='...'
uv sync --all-groups
uv run uvicorn hh_relay.app:app --reload
```

Не передавайте token в публичные endpoints и не добавляйте его в Git. Relay не вызывает `POST /token` во время работы: повторная выдача application token отзывает предыдущий, а hh.ru запрещает выпускать новый чаще одного раза в пять минут. `HH-User-Agent` уже задан в приложении как `hh-relay/1.0 (https://github.com/Syrenny/hh-relay)`.

## REST API

- `GET /api/health` — проверка relay без обращения за OAuth token;
- `GET /api/vacancies/search` — до 50 уникальных вакансий за последние 24 часа;
- `GET /api/vacancies/{vacancy_id}` — полная карточка вакансии.

Поиск принимает `text`, необязательный числовой `area` и необязательный `experience`: `noExperience`, `between1And3`, `between3And6` или `moreThan6`. Relay передаёт hh.ru границы последних 24 часов, сортировку по времени публикации и дополнительно проверяет точный cutoff, поскольку API округляет временные параметры.

```bash
curl http://127.0.0.1:8000/api/health
curl --get http://127.0.0.1:8000/api/vacancies/search \
  --data-urlencode 'text=Python FastAPI' \
  --data-urlencode 'area=1' \
  --data-urlencode 'experience=between1And3'
curl http://127.0.0.1:8000/api/vacancies/136199617
```

OpenAPI доступен по адресу `/openapi.json`. Упрощённая схема для Actions содержит только `healthCheck`, `searchVacancies` и `getVacancy`.

Поле `description` содержит недоверенный HTML от hh.ru и при отображении требует безопасной обработки. `creation_time` равен `null`, поскольку официальный API не предоставляет отдельное подтверждённое поле.

## Ошибки upstream

Relay возвращает стабильный объект `error`. Основные коды:

- `oauth_not_configured` — отсутствует `HH_ACCESS_TOKEN`;
- `upstream_unauthorized` — hh.ru отклонил настроенный application token;
- `upstream_forbidden`, `upstream_rate_limited` — ответы `403` и `429`;
- `upstream_timeout`, `upstream_http_error` — timeout и остальные transport/HTTP ошибки;
- `upstream_structure_changed` — JSON API не соответствует поддерживаемой схеме;
- `vacancy_not_found` — карточка вакансии не найдена.

Логи содержат только endpoint path без query, HTTP status, номер безопасной попытки и тип исключения. Токены, credentials, поисковый текст и upstream body не логируются.

## MCP для ChatGPT

Stateless Streamable HTTP endpoint `/mcp` предоставляет инструменты:

- `search_vacancies` — компактный поиск, исключающий уже классифицированные ID;
- `get_vacancy` — полная карточка по ID;
- `save_classified_vacancies` — идемпотентно сохраняет до 15 обработанных свежих вакансий с классификацией `S/A/B/C/rejected`.

Для опубликованного сервиса используйте `https://hh-relay.vercel.app/mcp` и вариант **No authentication**. Навыки находятся в `skills/find-python-backend-jobs/` и `skills/write-python-cover-letter/`.

Write-tool повторно получает каждую карточку с официального API hh.ru и не принимает от модели название, URL или описание. `rationale` обязателен для любой классификации, включая `rejected`. Все успешно сохранённые ID исключаются из последующих MCP-поисков; REST-поиск остаётся независимым от базы. В личной версии endpoint не использует OAuth, поэтому mutation дополнительно ограничена свежими каноническими вакансиями, batch size и строгой схемой. Не используйте этот вариант для чувствительных или многопользовательских данных.

## Персональный мониторинг

Закрытый dashboard доступен по `/dashboard`. Он группирует сохранённые вакансии по tier `S/A/B/C`; вакансию можно скрыть и позднее вернуть.

Интерфейс формируется FastAPI/Jinja и использует палитру Web Awesome без отдельного frontend-приложения. Поиск и оценку выполняет scheduled task ChatGPT с загруженным skill `find-python-backend-jobs`; готовый prompt находится в `skills/find-python-backend-jobs/SCHEDULED_TASK_PROMPT.md`.

### Внешние сервисы

- Neon PostgreSQL хранит вакансии и пользовательский признак «Скрыто»;
- ChatGPT через MCP ищет, оценивает и сохраняет вакансии;
- Vercel обслуживает relay, MCP и dashboard.

### Vercel Environment Variables

```text
HH_ACCESS_TOKEN
DATABASE_URL
DASHBOARD_USERNAME
DASHBOARD_PASSWORD
```

Все четыре значения задаются только на сервере; токен, URL базы и пароль являются секретами. Dashboard защищён HTTP Basic и должен использоваться только через HTTPS. Переменные прежнего monitor pipeline (`OPENAI_API_KEY`, `RESEND_API_KEY`, `OPENAI_MODEL`, `OPENAI_DAILY_TOKEN_BUDGET`) больше не используются и после успешной проверки deployment могут быть удалены.

Production deployment автоматически применяет миграции Alembic через `run.sh` до публикации новой Vercel-сборки. Скрипт пропускает preview/development environments и использует PostgreSQL advisory lock для защиты от параллельных production builds. Для ручного локального запуска:

```bash
DATABASE_URL='...' uv run alembic upgrade head
```

После deployment обновите подключение MCP plugin в ChatGPT, вручную запустите skill и проверьте цепочку `search_vacancies → get_vacancy → save_classified_vacancies → dashboard`. Повторный поиск не должен возвращать успешно классифицированные ID. Только после этого создавайте расписание из подготовленного prompt.

## Проверки

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
git diff --check
```

Тесты используют обезличенные JSON fixtures официального API и не обращаются к hh.ru.

## Деплой на Vercel

1. Импортируйте репозиторий с preset **FastAPI**.
2. Добавьте server-side Environment Variable `HH_ACCESS_TOKEN` для нужных environments. Значение возьмите на `https://dev.hh.ru/admin`.
3. Не задавайте Build Command и Output Directory.
4. Выполните deployment и проверьте health, REST search/detail и MCP.

После успешной миграции удалите прежние переменные `HH_CLIENT_ID`, `HH_CLIENT_SECRET` и `SINGBOX_VLESS_URL` из Vercel. Они больше не используются.
