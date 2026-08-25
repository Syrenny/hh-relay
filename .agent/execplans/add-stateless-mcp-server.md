# Stateless MCP-сервер для ChatGPT

## Цель

Добавить к существующему hh-relay удалённый MCP endpoint, который можно подключить к обычному ChatGPT и использовать из периодических задач. Сохранить REST API и Custom GPT Action без изменений.

## Принятые решения

- MCP работает без авторизации: данные публичные, инструменты только читают hh.ru.
- Дополнительный rate limiting не добавляется по прямому решению пользователя.
- Используется Streamable HTTP, stateless-режим и JSON responses, подходящие для serverless runtime Vercel.
- Публичный MCP URL: `https://hh-relay.vercel.app/mcp`.
- Существующие функциональные пределы поиска сохраняются: последние 24 часа, до 10 страниц и до 50 вакансий.

## Инструменты

### `search_vacancies`

Параметры:

- `text: str` — поисковый запрос;
- `area: int | None` — ID региона hh.ru;
- `experience: str | None` — одно из подтверждённых значений опыта.

Возвращает компактный структурированный результат без `snippet`: вакансии, `count`, `pages_fetched`, `truncated`, `cutoff`. Инструмент помечается `readOnlyHint: true`, `destructiveHint: false`.

### `get_vacancy`

Параметр `vacancy_id: int`. Возвращает полную карточку, включая HTML `description`, навыки и условия работы. Инструмент также read-only и недеструктивный.

## Архитектура

- Добавить официальный Python MCP SDK в `pyproject.toml` и `uv.lock`.
- Создать `src/hh_relay/mcp_server.py` с `FastMCP` в stateless-режиме.
- Каждый tool использует существующие `create_http_client`, `HHClient` и `VacancyService`; scraping и нормализация не дублируются.
- MCP ASGI application монтируется в существующее FastAPI-приложение по `/mcp` либо экспортируется через совместимый Vercel entrypoint — точный вариант выбирается после локального transport spike с учётом lifespan SDK.
- Ошибки relay преобразуются в MCP tool errors с исходным стабильным `code`; успешные ответы сериализуются через Pydantic `model_dump(mode="json", by_alias=True)`.
- REST endpoints `/api/*` и `/openapi.json` продолжают работать как прежде.

## Этапы

1. Зафиксировать совместимую версию Python MCP SDK через `uv` и проверить актуальный API stateless Streamable HTTP.
2. Реализовать два инструмента поверх существующего сервисного слоя.
3. Подключить MCP ASGI endpoint к приложению и Vercel routing без сессионного состояния процесса.
4. Добавить protocol-level тесты initialize, tools/list и tools/call, а также unit-тесты параметров и ошибок.
5. Обновить README инструкцией подключения URL к ChatGPT и примером периодической задачи.
6. Запустить Ruff, pytest, локальный MCP smoke test и после deployment проверить production initialize/tools/list/tools/call.

## Критерии приёмки

- POST/Streamable HTTP MCP initialize успешно отвечает на `/mcp`.
- `tools/list` содержит ровно `search_vacancies` и `get_vacancy` с read-only аннотациями.
- Оба инструмента возвращают структурированные JSON-данные существующих Pydantic-моделей.
- MCP не требует API key, OAuth или иных credentials и не применяет дополнительный rate limiting.
- MCP работает stateless между независимыми Vercel invocations.
- REST API, Action OpenAPI, Ruff и все существующие тесты не регрессируют.

## Риски

- MCP transport требует корректной обработки lifespan. Выбранная схема подключения должна быть подтверждена protocol-level тестом, а не только импортом модуля.
- Serverless runtime не гарантирует сохранение MCP-сессии. Поэтому сессионный transport не используется.
- Полная карточка может содержать большой HTML. ChatGPT должен сначала искать компактный список, затем вызывать `get_vacancy` только для выбранных ID.

## Решение, требующее утверждения

- ExecPlan утверждён пользователем 2026-08-25: MCP без авторизации и без дополнительного rate limiting, stateless Streamable HTTP по `/mcp`.

## Прогресс реализации

- 2026-08-25: через `uv` подключён и зафиксирован `mcp 1.29.1`; подтверждены нативные параметры `stateless_http` и `json_response`.
- 2026-08-25: реализованы `search_vacancies` и `get_vacancy` поверх существующего `VacancyService`, оба помечены read-only и недеструктивными.
- 2026-08-25: Streamable HTTP приложение смонтировано по `/mcp`, MCP lifespan объединён с FastAPI lifespan.
- 2026-08-25: добавлены protocol-level тесты `initialize`, `tools/list`, `tools/call` с structured output на обезличенном fixture.
- 2026-08-25: локальный live smoke test вернул `200` для всех трёх MCP методов; реальный `search_vacancies` вернул 12 вакансий, payload `tools/call` составил около 14,7 КБ.
