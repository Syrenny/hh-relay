from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Experience(StrEnum):
    NO_EXPERIENCE = "noExperience"
    BETWEEN_ONE_AND_THREE = "between1And3"
    BETWEEN_THREE_AND_SIX = "between3And6"
    MORE_THAN_SIX = "moreThan6"


class SearchQuery(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=512,
        description="Поисковый запрос, например Python FastAPI.",
    )
    area: int | None = Field(
        default=None,
        ge=1,
        description="Числовой ID региона hh.ru, например 1 для Москвы.",
    )
    experience: Experience | None = Field(
        default=None,
        description="Требуемый опыт работы в формате hh.ru.",
    )
    page: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Номер страницы; первая страница имеет номер 0.",
    )
    hours: int = Field(
        default=24,
        ge=1,
        le=24 * 30,
        description="Оставить вакансии за последние N часов.",
    )


class Employer(BaseModel):
    id: str | None = None
    name: str


class Area(BaseModel):
    id: str | None = None
    name: str


class Salary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: int | None = Field(default=None, serialization_alias="from")
    to: int | None = None
    currency: str | None = None
    gross: bool | None = None
    mode: str | None = None
    frequency: str | None = None


class Snippet(BaseModel):
    requirement: str | None = None
    responsibility: str | None = None
    conditions: str | None = None
    skills: str | None = None
    description: str | None = None


class Vacancy(BaseModel):
    id: str
    name: str
    url: HttpUrl
    employer: Employer | None = None
    area: Area | None = None
    salary: Salary | None = None
    experience: str | None = None
    published_at: datetime
    creation_time: datetime | None = None
    snippet: Snippet | None = None


class SearchResponse(BaseModel):
    count: int
    vacancies: list[Vacancy]


class HealthResponse(BaseModel):
    status: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class UpstreamLinks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    desktop: str | None = None
    mobile: str | None = None


class UpstreamCompany(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | str | None = None
    name: str | None = None
    visible_name: str | None = Field(default=None, alias="visibleName")


class UpstreamArea(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | str | None = Field(default=None, alias="@id")
    name: str


class UpstreamCompensation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_: int | None = Field(default=None, alias="from")
    to: int | None = None
    currency_code: str | None = Field(default=None, alias="currencyCode")
    gross: bool | None = None
    mode: str | None = None
    frequency: str | None = None


class UpstreamPublicationTime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: datetime = Field(alias="$")
    timestamp: int | None = Field(default=None, alias="@timestamp")


class UpstreamSnippet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    req: str | None = None
    resp: str | None = None
    cond: str | None = None
    skill: str | None = None
    desc: str | None = None


class UpstreamVacancy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancy_id: int | str = Field(alias="vacancyId")
    name: str
    links: UpstreamLinks
    view_url: str | None = Field(default=None, alias="viewUrl")
    company: UpstreamCompany | None = None
    area: UpstreamArea | None = None
    compensation: UpstreamCompensation | None = None
    work_experience: str | None = Field(default=None, alias="workExperience")
    publication_time: UpstreamPublicationTime = Field(alias="publicationTime")
    creation_time: datetime | None = Field(default=None, alias="creationTime")
    snippet: UpstreamSnippet | None = None


class UpstreamSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancies: list[UpstreamVacancy]


class UpstreamInitialState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancy_search_result: UpstreamSearchResult = Field(alias="vacancySearchResult")
