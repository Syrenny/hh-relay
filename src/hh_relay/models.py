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


class Employer(BaseModel):
    id: str | None = None
    name: str


class Area(BaseModel):
    id: str | None = None
    name: str


class Salary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

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


class VacancySummary(BaseModel):
    id: str
    name: str
    url: HttpUrl
    employer: Employer | None = None
    area: Area | None = None
    salary: Salary | None = None
    experience: str | None = None
    published_at: datetime
    creation_time: datetime | None = None


class Vacancy(VacancySummary):
    snippet: Snippet | None = None


class SearchResponse(BaseModel):
    count: int
    vacancies: list[VacancySummary]
    pages_fetched: int
    truncated: bool
    cutoff: datetime


class Address(BaseModel):
    display_name: str | None = None
    city: str | None = None
    street: str | None = None


class VacancyDetail(Vacancy):
    description: str
    valid_through: datetime | None = None
    key_skills: list[str]
    address: Address | None = None
    employment_form: str | None = None
    work_formats: list[str]
    work_schedule_by_days: list[str]
    working_hours: list[str]


class HealthResponse(BaseModel):
    status: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HHReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str


class HHEmployer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str


class HHSalary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_: int | None = Field(default=None, alias="from")
    to: int | None = None
    currency: str | None = None
    gross: bool | None = None
    mode: HHReference | None = None
    frequency: HHReference | None = None


class HHSnippet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirement: str | None = None
    responsibility: str | None = None


class HHVacancy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    alternate_url: str
    employer: HHEmployer | None = None
    area: HHReference | None = None
    salary_range: HHSalary | None = None
    salary: HHSalary | None = None
    experience: HHReference | None = None
    published_at: datetime
    snippet: HHSnippet | None = None


class HHSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[HHVacancy]
    page: int
    pages: int
    per_page: int
    found: int


class HHAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw: str | None = None
    city: str | None = None
    street: str | None = None


class HHKeySkill(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class HHVacancyDetail(HHVacancy):
    model_config = ConfigDict(extra="ignore")

    description: str
    expires_at: datetime | None = None
    key_skills: list[HHKeySkill] = Field(default_factory=list)
    address: HHAddress | None = None
    employment_form: HHReference | None = None
    work_format: list[HHReference] = Field(default_factory=list)
    work_schedule_by_days: list[HHReference] = Field(default_factory=list)
    working_hours: list[HHReference] = Field(default_factory=list)


class HHTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str
    expires_in: int | None = Field(default=None, gt=0)
