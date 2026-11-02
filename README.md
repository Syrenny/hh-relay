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

Stateless Streamable HTTP endpoint `/mcp` предоставляет два read-only инструмента:

- `search_vacancies` — компактный поиск;
- `get_vacancy` — полная карточка по ID.

Для опубликованного сервиса используйте `https://hh-relay.vercel.app/mcp` и вариант **No authentication**. Навыки находятся в `skills/find-python-backend-jobs/` и `skills/write-python-cover-letter/`.

## Персональный мониторинг

Закрытый dashboard доступен по `/dashboard`. Он показывает найденные вакансии, оценку соответствия и пользовательские статусы `Новая`, `Интересная`, `Откликнулся`, `Не подходит` и `Архив`. На странице вакансии можно сгенерировать сопроводительное письмо по правилам из `skills/write-python-cover-letter/`.

Интерфейс формируется FastAPI/Jinja и использует Web Awesome без отдельного frontend-приложения. Мониторинг запускается GitHub Actions каждый час с 07:17 до 23:17 по Новосибирску и один раз ночью. При отсутствии новых подходящих вакансий письмо не отправляется.

### Внешние сервисы

- Neon PostgreSQL хранит вакансии, статусы, письма и историю запусков;
- OpenAI Responses API оценивает вакансии и пишет письма;
- Resend отправляет email;
- GitHub Actions выполняет длительный monitor script вне лимита Vercel Function.

Создайте OpenAI project и включите подходящую настройку sharing inputs/outputs в API Platform, если хотите использовать доступные организации complimentary tokens. По умолчанию используется eligible-модель `gpt-5.4-mini`; код не переключается на другую платную модель автоматически.

### Vercel Environment Variables

```text
DATABASE_URL
OPENAI_API_KEY
DASHBOARD_USERNAME
DASHBOARD_PASSWORD
```

`DATABASE_URL`, `OPENAI_API_KEY` и пароль являются секретами. Dashboard защищён HTTP Basic и должен использоваться только через HTTPS. Дневной предел по умолчанию равен 250 000 токенов. Модель и предел можно необязательно переопределить через `OPENAI_MODEL` и `OPENAI_DAILY_TOKEN_BUDGET`.

Перед deployment примените миграции Alembic:

```bash
DATABASE_URL='...' uv run alembic upgrade head
```

### GitHub Actions

Добавьте repository secrets:

- `DATABASE_URL`;
- `OPENAI_API_KEY`;
- `RESEND_API_KEY`.

Добавьте repository variables:

- `EMAIL_FROM` и `EMAIL_TO`;
- `DASHBOARD_BASE_URL`, например `https://hh-relay.vercel.app/dashboard`;
- `HH_RELAY_BASE_URL`, например `https://hh-relay.vercel.app`.

Sender в `EMAIL_FROM` должен быть разрешён настройками Resend. Первый запуск выполните вручную через workflow **Vacancy monitor**, затем проверьте запись вакансий, dashboard и доставку письма.

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
