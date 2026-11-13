from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Experience(StrEnum):
    NO_EXPERIENCE = "noExperience"
    BETWEEN_ONE_AND_THREE = "between1And3"
    BETWEEN_THREE_AND_SIX = "between3And6"
    MORE_THAN_SIX = "moreThan6"


class VacancyTier(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    REJECTED = "rejected"


class SearchSettings(BaseModel):
    queries: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1,
        max_length=30,
    )
    experiences: list[Experience] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "SearchSettings":
        normalized = [query.strip() for query in self.queries]
        if any(not query for query in normalized):
            msg = "Search queries must not be blank"
            raise ValueError(msg)
        if len({query.casefold() for query in normalized}) != len(normalized):
            msg = "Search queries must be unique"
            raise ValueError(msg)
        if len(set(self.experiences)) != len(self.experiences):
            msg = "Search experiences must be unique"
            raise ValueError(msg)
        self.queries = normalized
        return self


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
    total_count: int
    vacancies: list[VacancySummary]
    next_cursor: str | None = None
    queries_executed: int
    pages_fetched: int
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


ShortNote = Annotated[str, Field(min_length=1, max_length=300)]


class ClassifiedVacancy(BaseModel):
    vacancy_id: int = Field(ge=1)
    tier: VacancyTier
    rationale: str = Field(min_length=1, max_length=1000)
    requirements: list[ShortNote] = Field(default_factory=list, max_length=10)
    warnings: list[ShortNote] = Field(default_factory=list, max_length=10)


class SaveFailure(BaseModel):
    vacancy_id: int
    code: str


class SaveClassifiedVacanciesResult(BaseModel):
    created: list[int] = Field(default_factory=list)
    updated: list[int] = Field(default_factory=list)
    unchanged: list[int] = Field(default_factory=list)
    failed: list[SaveFailure] = Field(default_factory=list)


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
