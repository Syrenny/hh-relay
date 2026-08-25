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
    is_adv: bool = Field(default=False, alias="@isAdv")
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
    paging: "UpstreamPaging | None" = None


class UpstreamPagingNext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page: int
    disabled: bool


class UpstreamPaging(BaseModel):
    model_config = ConfigDict(extra="ignore")

    next: UpstreamPagingNext


class UpstreamInitialState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancy_search_result: UpstreamSearchResult = Field(alias="vacancySearchResult")


class UpstreamAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    display_name: str | None = Field(default=None, alias="displayName")
    city: str | None = None
    street: str | None = None


class UpstreamKeySkills(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key_skill: list[str] = Field(default_factory=list, alias="keySkill")


class UpstreamVacancyDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancy_id: int | str = Field(alias="vacancyId")
    name: str
    description: str
    publication_date: datetime = Field(alias="publicationDate")
    valid_through_time: datetime | None = Field(default=None, alias="validThroughTime")
    work_experience: str | None = Field(default=None, alias="workExperience")
    company: UpstreamCompany | None = None
    area: UpstreamArea | None = None
    compensation: UpstreamCompensation | None = None
    key_skills: UpstreamKeySkills | None = Field(default=None, alias="keySkills")
    address: UpstreamAddress | None = None
    employment_form: str | None = Field(default=None, alias="employmentForm")
    work_formats: list[str] = Field(default_factory=list, alias="workFormats")
    work_schedule_by_days: list[str] = Field(
        default_factory=list,
        alias="workScheduleByDays",
    )
    working_hours: list[str] = Field(default_factory=list, alias="workingHours")


class UpstreamVacancyDetailState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vacancy_view: UpstreamVacancyDetail = Field(alias="vacancyView")
