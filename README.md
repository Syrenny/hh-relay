# hh-relay

Небольшой FastAPI-прокси для Custom GPT Action. Он ищет вакансии через обычную SSR-страницу `https://hh.ru/search/vacancy` и не обращается к `api.hh.ru`.

Приложение извлекает `<template id="HH-Lux-InitialState">`, выполняет `html.unescape` и `json.loads`, затем читает подтверждённый путь `vacancySearchResult.vacancies`. Ответ нормализуется, фильтруется по времени публикации и очищается от дублей по ID вакансии.

## Требования

- Python 3.13;
- [`uv`](https://docs.astral.sh/uv/).

## Локальный запуск

Установить зафиксированные зависимости:

```bash
uv sync --all-groups
```

Запустить приложение:

```bash
uv run uvicorn hh_relay.app:app --reload
```

Документация OpenAPI будет доступна по адресу `http://127.0.0.1:8000/docs`, а схема для Custom GPT Action — по адресу `http://127.0.0.1:8000/openapi.json`.

Проверить приложение:

```bash
curl http://127.0.0.1:8000/api/health
curl --get http://127.0.0.1:8000/api/vacancies/search \
  --data-urlencode 'text=Python FastAPI' \
  --data-urlencode 'area=1' \
  --data-urlencode 'experience=between1And3' \
  --data-urlencode 'page=0' \
  --data-urlencode 'hours=24'
```

## API

### `GET /api/health`

Проверяет готовность приложения и не делает запрос к hh.ru.

### `GET /api/vacancies/search`

Параметры:

| Параметр | Обязательный | Значение |
|---|---:|---|
| `text` | да | Строка поиска, от 1 до 512 символов |
| `area` | нет | Числовой ID региона hh.ru |
| `experience` | нет | `noExperience`, `between1And3`, `between3And6` или `moreThan6` |
| `page` | нет | Номер страницы от `0` до `100`, по умолчанию `0` |
| `hours` | нет | Возраст публикации от `1` до `720` часов, по умолчанию `24` |

Пример сокращённого ответа:

```json
{
  "count": 1,
  "vacancies": [
    {
      "id": "136199617",
      "name": "Senior Python Engineer",
      "url": "https://hh.ru/vacancy/136199617",
      "employer": {
        "id": "12725876",
        "name": "Example Employer"
      },
      "area": {
        "id": "1",
        "name": "Москва"
      },
      "salary": {
        "from": 250000,
        "to": 300000,
        "currency": "RUR",
        "gross": false,
        "mode": "MONTH",
        "frequency": "MONTHLY"
      },
      "experience": "moreThan6",
      "published_at": "2026-08-25T09:43:49.423+03:00",
      "creation_time": "2026-08-13T09:43:49.423+03:00",
      "snippet": {
        "requirement": "Python, async/await",
        "responsibility": "Backend development",
        "conditions": null,
        "skills": "Python, FastAPI",
        "description": null
      }
    }
  ]
}
```

Фильтр `hours` использует `publicationTime["$"]`. Дубли удаляются по `vacancyId` с сохранением порядка hh.ru.

## Ошибки upstream

Приложение возвращает стабильный объект `error`:

- `502 upstream_forbidden` — hh.ru ответил `403`;
- `504 upstream_timeout` — превышен timeout;
- `502 upstream_structure_changed` — отсутствует template, JSON повреждён или SSR-схема изменилась;
- `502 upstream_http_error` — другая сетевая или HTTP-ошибка hh.ru.

Невалидные query-параметры возвращают стандартный ответ FastAPI `422`.

## Проверки

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Тесты используют минимальный обезличенный fixture с фактическими именами полей SSR-состояния и не обращаются к hh.ru.

## Деплой на Vercel

1. Импортировать GitHub-репозиторий в Vercel через **Add New → Project**.
2. Оставить preset **FastAPI** и корневую директорию `./`.
3. Не задавать Build Command, Output Directory и переменные окружения.
4. Нажать **Deploy**.

Vercel использует `api/index.py`, `pyproject.toml`, `uv.lock` и `vercel.json`. Push в `main` создаёт production deployment, а ветки и pull request — preview deployment.

После деплоя проверить:

```bash
curl https://YOUR_PROJECT.vercel.app/api/health
curl --get https://YOUR_PROJECT.vercel.app/api/vacancies/search \
  --data-urlencode 'text=Python' \
  --data-urlencode 'area=1' \
  --data-urlencode 'hours=24'
```

SSR-схема hh.ru не является публичным контрактом. Если hh.ru изменит HTML или JSON, endpoint вернёт `upstream_structure_changed`, а parser потребуется обновить по новому фактическому образцу.
