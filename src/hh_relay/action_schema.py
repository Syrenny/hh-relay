from typing import Any, Final

PRODUCTION_URL: Final = "https://hh-relay.vercel.app"


def build_action_schema() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "hh.ru Vacancy Relay",
            "description": (
                "Поиск свежих вакансий на hh.ru и получение полной карточки."
            ),
            "version": "1.0.0",
        },
        "servers": [{"url": PRODUCTION_URL}],
        "paths": {
            "/api/health": {
                "get": {
                    "operationId": "healthCheck",
                    "summary": "Проверить доступность сервиса",
                    "responses": {
                        "200": {
                            "description": "Сервис доступен",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                        },
                                        "required": ["status"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/vacancies/search": {
                "get": {
                    "operationId": "searchVacancies",
                    "summary": "Найти вакансии за последние 24 часа",
                    "description": (
                        "Возвращает не более 50 свежих вакансий. Для полного "
                        "описания вызовите getVacancy, передав полученный ID."
                    ),
                    "parameters": [
                        {
                            "name": "text",
                            "in": "query",
                            "required": True,
                            "description": "Поисковый запрос, например Python backend.",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "area",
                            "in": "query",
                            "required": False,
                            "description": "ID региона hh.ru, например 1 для Москвы.",
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        {
                            "name": "experience",
                            "in": "query",
                            "required": False,
                            "description": "Требуемый опыт работы.",
                            "schema": {
                                "type": "string",
                                "enum": [
                                    "noExperience",
                                    "between1And3",
                                    "between3And6",
                                    "moreThan6",
                                ],
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Результаты поиска",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/SearchResponse"
                                    }
                                }
                            },
                        },
                        "502": {"description": "Ошибка ответа hh.ru"},
                        "504": {"description": "Timeout ответа hh.ru"},
                    },
                }
            },
            "/api/vacancies/{vacancy_id}": {
                "get": {
                    "operationId": "getVacancy",
                    "summary": "Получить полную карточку вакансии",
                    "parameters": [
                        {
                            "name": "vacancy_id",
                            "in": "path",
                            "required": True,
                            "description": "ID вакансии из searchVacancies.",
                            "schema": {"type": "integer", "minimum": 1},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Полная карточка вакансии",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/VacancyDetail"
                                    }
                                }
                            },
                        },
                        "404": {"description": "Вакансия не найдена"},
                        "502": {"description": "Ошибка ответа hh.ru"},
                        "504": {"description": "Timeout ответа hh.ru"},
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "VacancySummary": {
                    "type": "object",
                    "description": "Краткая вакансия без snippet и полного описания.",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                        "employer": {"type": ["object", "null"]},
                        "area": {"type": ["object", "null"]},
                        "salary": {"type": ["object", "null"]},
                        "experience": {"type": ["string", "null"]},
                        "published_at": {"type": "string"},
                        "creation_time": {"type": ["string", "null"]},
                    },
                    "required": ["id", "name", "url", "published_at"],
                },
                "SearchResponse": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "vacancies": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/VacancySummary"},
                        },
                        "pages_fetched": {"type": "integer"},
                        "truncated": {"type": "boolean"},
                        "cutoff": {"type": "string"},
                    },
                    "required": [
                        "count",
                        "vacancies",
                        "pages_fetched",
                        "truncated",
                        "cutoff",
                    ],
                },
                "VacancyDetail": {
                    "type": "object",
                    "description": (
                        "Полная карточка. Поле description содержит HTML от hh.ru."
                    ),
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                        "description": {"type": "string"},
                        "published_at": {"type": "string"},
                        "employer": {"type": ["object", "null"]},
                        "area": {"type": ["object", "null"]},
                        "salary": {"type": ["object", "null"]},
                        "experience": {"type": ["string", "null"]},
                        "key_skills": {"type": "array", "items": {"type": "string"}},
                        "address": {"type": ["object", "null"]},
                        "employment_form": {"type": ["string", "null"]},
                        "work_formats": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["id", "name", "url", "description", "published_at"],
                },
            }
        },
    }
