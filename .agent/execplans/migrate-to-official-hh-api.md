# Переход на официальный API hh.ru

## Статус реализации

Реализация завершена 2026-09-01.

- [x] Добавлены минимальные Pydantic-модели token, search и vacancy detail.
- [x] Реализован конкурентно-безопасный application token manager и однократное обновление после `401`.
- [x] REST и MCP переведены на официальный `api.hh.ru` с сохранением публичных успешных ответов.
- [x] Поиск передаёт временное окно API и дополнительно применяет точный cutoff 24 часа.
- [x] HTML fixtures заменены обезличенными JSON fixtures официального API.
- [x] Удалены SSR parser, `sing-box`, VLESS, proxy health, install script и SOCKS dependency.
- [x] README и Vercel-конфигурация обновлены для `HH_CLIENT_ID` и `HH_CLIENT_SECRET`.
- [x] Ruff, pytest, `git diff --check` и валидация `vercel.json` пройдены.
- [ ] После deployment проверить health, REST search/detail и MCP initialize/tools/list/tools/call, затем удалить `SINGBOX_VLESS_URL` из Vercel.

Локальная проверка: `25 passed`; `ruff format --check`, `ruff check` и `git diff --check` завершились успешно. `vercel.json` проверен по схеме `https://openapi.vercel.sh/vercel.json` через Draft 7 validator.

## Цель

Заменить SSR scraping и VLESS-прокси официальным `api.hh.ru` с OAuth 2.0 Client Credentials после одобрения приложения. Сохранить публичный REST API, OpenAPI для ChatGPT Action, оба MCP-инструмента и формат их успешных ответов.

## Подтверждённый контракт hh.ru

План основан на актуальной официальной OpenAPI 3.0.3 спецификации `https://api.hh.ru/openapi/specification/public`, проверенной 2026-09-01.

- Токен приложения получается через `POST https://api.hh.ru/token`.
- Content-Type: `application/x-www-form-urlencoded`.
- Поля: `grant_type=client_credentials`, `client_id`, `client_secret`.
- Успешный ответ приложения содержит `access_token` и `token_type=bearer`; `expires_in` для application token спецификацией не гарантируется.
- Авторизованные запросы передают `Authorization: Bearer <token>`.
- `GET /vacancies` поддерживает `text`, `area`, `experience`, `page`, `per_page`, `date_from`, `date_to` и `order_by`.
- `date_from` и `date_to` принимают ISO 8601 с точностью до секунды, но hh.ru округляет значение до пяти минут.
- `GET /vacancies/{vacancy_id}` возвращает полную карточку вакансии.
- Для API-запросов требуется идентифицирующий заголовок `HH-User-Agent`.

## Конфигурация

Использовать только серверные Vercel Environment Variables:

- `HH_CLIENT_ID` — идентификатор одобренного приложения;
- `HH_CLIENT_SECRET` — секрет приложения;

Заголовок `HH-User-Agent` не настраивать через environment variable. Захардкодить публичный идентификатор приложения `hh-relay/1.0 (https://github.com/Syrenny/hh-relay)` в клиенте hh.ru. Это не секрет: значение только идентифицирует приложение и содержит публичный адрес для связи/диагностики.

Не принимать credentials через публичные endpoints, не возвращать их в ответах и не писать значения в логи. Удалить `SINGBOX_VLESS_URL` после успешного перехода production.

## Авторизация

Добавить конкурентно-безопасный менеджер application token:

- получать токен лениво при первом обращении к hh.ru;
- не запрашивать токен для `/api/health`;
- переиспользовать токен в пределах тёплого serverless-инстанса;
- не предполагать срок действия, если `expires_in` отсутствует;
- при `401` один раз инвалидировать токен, получить новый и повторить исходный запрос;
- не повторять ошибочные credentials и другие постоянные OAuth-ошибки в рамках одного запроса;
- преобразовывать отсутствие конфигурации и отказ OAuth в стабильные безопасные ошибки relay.

## Поиск вакансий

Публичный `GET /api/vacancies/search` сохраняет параметры `text`, `area`, `experience`.

Внутренний запрос к `GET https://api.hh.ru/vacancies` передаёт:

- `text`, `area`, `experience` из публичного запроса;
- `date_from=now-24h` и `date_to=now`;
- `order_by=publication_time`;
- внутренние `page` и `per_page`.

Сервис дополнительно сравнивает фактический `published_at` с точным cutoff, поскольку API округляет временные параметры. Дедупликация по ID, максимум 50 ответов, внутренний предел страниц, `pages_fetched`, `truncated` и `cutoff` сохраняются. `truncated=true`, если API сообщает о следующих страницах или найдено больше 50 подходящих уникальных вакансий.

## Нормализация

Сохранить текущие публичные модели:

- поиск: `id`, `name`, `url`, `employer`, `area`, `salary`, `experience`, `published_at`, `creation_time`;
- детали: те же поля плюс `description`, `valid_through`, `key_skills`, `address`, `employment_form`, `work_formats`, `work_schedule_by_days`, `working_hours`.

Источники полей брать только из фактических официальных JSON-схем и ответов:

- URL представления — `alternate_url`;
- зарплата — преимущественно `salary_range`, с совместимостью с документированным deprecated `salary` при необходимости;
- опыт — объект `experience.id`;
- навыки и форматы — документированные объекты полной карточки;
- `creation_time` возвращать `null`, если официальный API не предоставляет отдельного подтверждённого поля.

Не выдумывать эквиваленты отсутствующих SSR-полей.

## Ошибки

Добавить стабильные ошибки без upstream body и секретов:

- отсутствующая OAuth-конфигурация;
- отказ получения application token;
- `401` после повторной авторизации;
- `403`, `404`, `429`, timeout и другие HTTP/transport ошибки API.

В логах разрешены только endpoint path без query, HTTP status, номер безопасной попытки и тип исключения. Authorization header, client credentials, access token, поисковый текст и полные upstream responses не логировать.

## Удаляемая реализация

После реализации официального клиента удалить:

- `src/hh_relay/sing_box.py`;
- `scripts/install_sing_box.py` и директорию `scripts`, если она станет пустой;
- `/api/proxy-health` и его модели;
- VLESS parsing и SOCKS-зависимость `httpx[socks]`;
- buildCommand и `includeFiles` для бинарника из `vercel.json`;
- SSR parser, upstream SSR-модели и HTML fixtures, которые больше не используются;
- ошибки и документацию `upstream_proxy_unavailable`, `HH-Lux-InitialState` и VLESS;
- игнорирование сгенерированного `sing-box` в `.gitignore`.

Удалять только после того, как REST и MCP используют официальный клиент и тесты подтверждают новый путь.

## Этапы

1. Зафиксировать минимальные Pydantic-модели официальных token, search и vacancy detail ответов по OpenAPI-схеме.
2. Реализовать token manager и авторизованный `HHClient` с однократным обновлением после `401`.
3. Переписать поиск и нормализацию на официальные JSON-поля, сохранив публичный контракт.
4. Подключить один официальный клиент к REST и MCP без proxy.
5. Заменить HTML fixtures официальными обезличенными JSON fixtures и обновить unit/protocol tests.
6. Удалить SSR, `sing-box`, VLESS и связанные build/dependency файлы.
7. Обновить README настройкой OAuth и миграцией Vercel environment variables.
8. Запустить Ruff, pytest, `git diff --check` и проверить `vercel.json` по актуальной JSON Schema.
9. После deployment проверить health, REST search/detail и MCP initialize/tools/list/tools/call.

## Критерии приёмки

- `/api/health` работает без OAuth-запроса.
- Первый поиск получает application token и использует Bearer authorization и `HH-User-Agent`.
- Для `HH-User-Agent` используется захардкоженный публичный идентификатор приложения; отдельная environment variable не требуется.
- Параллельные холодные запросы не создают несколько одновременных token requests.
- `401` вызывает ровно одно обновление токена и один повтор исходного запроса.
- REST search/detail и MCP сохраняют текущие публичные успешные ответы.
- Поиск возвращает только вакансии не старше точного cutoff 24 часа и корректный `truncated`.
- В репозитории и deployment больше нет `sing-box`, VLESS, SSR parsing и SOCKS extras.
- Секреты и токены отсутствуют в Git, ответах и логах.
- Ruff, все тесты и `git diff --check` проходят.

## Риски

- Application token не содержит `expires_in`; поэтому обновление строится на `401`, а не на выдуманном TTL.
- Официальные search/detail модели отличаются от SSR, особенно зарплатой и форматами работы; нормализация должна опираться на актуальную схему и fixtures.
- Временные фильтры API округляются до пяти минут; точный cutoff остаётся на стороне relay.
- После удаления proxy rollback потребует предыдущего commit, поэтому production-проверку проводить сразу после deployment.

## Решение, требующее утверждения

- Утвердить полный переход на OAuth Client Credentials и официальный `api.hh.ru` с удалением SSR и VLESS реализации при сохранении публичного REST/MCP-контракта.
