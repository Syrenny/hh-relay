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

В опубликованный Custom GPT Action схему можно импортировать напрямую:

```text
https://hh-relay.vercel.app/openapi.json
```

Аутентификация для Action не требуется.

Проверить приложение:

```bash
curl http://127.0.0.1:8000/api/health
curl --get http://127.0.0.1:8000/api/vacancies/search \
  --data-urlencode 'text=Python FastAPI' \
  --data-urlencode 'area=1' \
  --data-urlencode 'experience=between1And3'
curl http://127.0.0.1:8000/api/vacancies/136199617
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

Сервис сам запрашивает страницы в порядке времени публикации, пока не достигнет границы последних 24 часов. Внутренний предел обхода — 10 страниц, а в ответ возвращается максимум 50 самых свежих уникальных вакансий, чтобы результат надёжно обрабатывался Custom GPT Action.

Пример сокращённого ответа:

```json
{
  "count": 1,
  "pages_fetched": 2,
  "truncated": false,
  "cutoff": "2026-08-24T14:00:00Z",
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

Cutoff вычисляется один раз как `now - 24h` и сравнивается с `publicationTime["$"]`. Дубли удаляются по `vacancyId` с сохранением порядка hh.ru. Старые рекламные вставки `@isAdv` фильтруются, но не вызывают преждевременную остановку пагинации. `truncated=true` означает, что найдено больше 50 подходящих вакансий либо предел в 10 страниц достигнут раньше cutoff или конца выдачи.

### `GET /api/vacancies/{vacancy_id}`

Возвращает полную карточку из `vacancyView`: основную информацию, полное HTML-описание, срок публикации, ключевые навыки, адрес и параметры формата работы.

```bash
curl http://127.0.0.1:8000/api/vacancies/136199617
```

HTML в поле `description` возвращается без исполнения и преобразования. При отображении его следует обрабатывать как недоверенные данные.

## Ошибки upstream

Приложение возвращает стабильный объект `error`:

- `502 upstream_forbidden` — hh.ru ответил `403`;
- `504 upstream_timeout` — превышен timeout;
- `502 upstream_structure_changed` — отсутствует template, JSON повреждён или SSR-схема изменилась;
- `502 upstream_http_error` — другая сетевая или HTTP-ошибка hh.ru.
- `404 vacancy_not_found` — карточка вакансии не найдена.

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
  --data-urlencode 'area=1'
curl https://YOUR_PROJECT.vercel.app/api/vacancies/136199617
```

SSR-схема hh.ru не является публичным контрактом. Если hh.ru изменит HTML или JSON, endpoint вернёт `upstream_structure_changed`, а parser потребуется обновить по новому фактическому образцу.
