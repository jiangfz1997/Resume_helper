from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class ProficiencyLevel(str, Enum):
    EXPERT = "expert"
    INTERMEDIATE = "intermediate"
    BEGINNER = "beginner"


class WorkExperience(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str | None = None
    gpa: str | None = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    url: str | None = None


class Skill(BaseModel):
    category: str
    name: str
    proficiency: ProficiencyLevel | None = None


class ResumeSkillGroup(BaseModel):
    """A resume-ready skill line; deliberately carries no proficiency rating."""

    category: str
    items: list[str] = Field(default_factory=list)


class CandidateProfileInput(BaseModel):
    schema_version: Literal[1] = 1
    # Kept optional-at-rest for profiles created before JSON import existed.
    # The cloud importer requires a non-empty name before it sends a PUT.
    full_name: str = ""
    summary: str | None = None
    contact_info: ContactInfo | None = None
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    resume_skills: list[ResumeSkillGroup] = Field(default_factory=list)
    # Legacy structured skills are retained for compatibility and possible
    # future scoring use. Resume rendering should prefer resume_skills.
    skills: list[Skill] = Field(default_factory=list)


class CandidateProfile(CandidateProfileInput):
    user_id: str
    profile_version: int = Field(ge=1)
    updated_at: datetime


class ApplicationSourceType(str, Enum):
    DASHBOARD = "dashboard"
    MANUAL = "manual"


class ApplicationStatus(str, Enum):
    APPLIED = "applied"
    RESUME_REJECTED = "resume_rejected"
    INTERVIEWING = "interviewing"
    INTERVIEW_REJECTED = "interview_rejected"
    OFFER = "offer"
    ACCEPTED = "accepted"
    WITHDRAWN = "withdrawn"


class ExtractionStatus(str, Enum):
    READY = "ready"
    EXTRACTING = "extracting"
    FAILED = "failed"


class ApplicationStatusEvent(BaseModel):
    status: ApplicationStatus
    note: str | None = None
    changed_at: datetime


class CreateApplicationFromJob(BaseModel):
    job_id: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    company: str
    title: str
    location: str | None = None
    jd_text: str


class CreateApplicationFromUrl(BaseModel):
    url: str


class UpdateApplicationStatus(BaseModel):
    status: ApplicationStatus
    note: str | None = None


class UpdateApplicationFields(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    notes: str | None = None


class JobApplication(BaseModel):
    application_id: str
    user_id: str
    source_type: ApplicationSourceType
    job_id: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    company: str
    title: str
    location: str | None = None
    jd_text: str
    raw_html: str | None = None
    status: ApplicationStatus
    status_history: list[ApplicationStatusEvent] = Field(default_factory=list)
    extraction_status: ExtractionStatus = ExtractionStatus.READY
    extraction_error: str | None = None
    notes: str | None = None
    applied_at: datetime
    created_at: datetime
    updated_at: datetime


class FetchStrategy(str, Enum):
    """Which reader produced a FetchedPage. Stored on the model rather than
    inferred from the URL later so a support question about one bad record
    can be answered from the record itself."""

    HTML = "html"
    WORKDAY_CXS = "workday_cxs"


class FetchedPage(BaseModel):
    """What a PageFetcher returns. Carries text separately from raw_html
    because the two no longer come from one document: a Workday posting is
    read from a JSON API, where the only markup is the description fragment
    and there is no page HTML to snapshot."""

    text: str
    raw_html: str | None = None
    fetch_strategy: FetchStrategy = FetchStrategy.HTML


class ExtractedJobInfo(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    jd_text: str
