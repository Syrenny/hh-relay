# hh-relay

FastAPI relay для Custom GPT Action и MCP, который ищет вакансии через официальный `api.hh.ru`. Публичные клиенты relay не проходят авторизацию: сервер самостоятельно получает application token по OAuth 2.0 Client Credentials.

## Требования и настройка

- Python 3.13;
- [`uv`](https://docs.astral.sh/uv/);
- одобренное приложение hh.ru с `client_id` и `client_secret`.

Credentials задаются только в окружении сервера:

```bash
export HH_CLIENT_ID='...'
export HH_CLIENT_SECRET='...'
uv sync --all-groups
uv run uvicorn hh_relay.app:app --reload
```

Не передавайте credentials в публичные endpoints и не добавляйте их в Git. `HH-User-Agent` уже задан в приложении как `hh-relay/1.0 (https://github.com/Syrenny/hh-relay)`.

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

- `oauth_not_configured` — отсутствуют `HH_CLIENT_ID` или `HH_CLIENT_SECRET`;
- `oauth_token_error` — hh.ru отказал в получении application token;
- `upstream_unauthorized` — повторная авторизация после `401` не помогла;
- `upstream_forbidden`, `upstream_rate_limited` — ответы `403` и `429`;
- `upstream_timeout`, `upstream_http_error` — timeout и остальные transport/HTTP ошибки;
- `upstream_structure_changed` — JSON API не соответствует поддерживаемой схеме;
- `vacancy_not_found` — карточка вакансии не найдена.

Логи содержат только endpoint path без query, HTTP status, номер безопасной попытки и тип исключения. Токены, credentials, поисковый текст и upstream body не логируются.

## MCP для ChatGPT

Stateless Streamable HTTP endpoint `/mcp` предоставляет два read-only инструмента:

- `search_vacancies` — компактный поиск;
- `get_vacancy` — полная карточка по ID.

Для опубликованного сервиса используйте `https://hh-relay.vercel.app/mcp` и вариант **No authentication**. Навыки находятся в `skills/find-python-backend-jobs/` и `skills/write-python-cover-letter/`.

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
2. Добавьте server-side Environment Variables `HH_CLIENT_ID` и `HH_CLIENT_SECRET` для нужных environments.
3. Не задавайте Build Command и Output Directory.
4. Выполните deployment и проверьте health, REST search/detail и MCP.

После успешной миграции удалите прежнюю переменную `SINGBOX_VLESS_URL` из Vercel. Она больше не используется.
