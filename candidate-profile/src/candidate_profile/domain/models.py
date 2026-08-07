from __future__ import annotations

from datetime import datetime
from enum import Enum

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
    name: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    url: str | None = None


class Skill(BaseModel):
    category: str
    name: str
    proficiency: ProficiencyLevel | None = None


class CandidateProfileInput(BaseModel):
    full_name: str = ""
    summary: str | None = None
    contact_info: ContactInfo | None = None
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)


class CandidateProfile(CandidateProfileInput):
    user_id: str
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


class ExtractedJobInfo(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    jd_text: str


class ApplicationStats(BaseModel):
    today: int
    this_week: int
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
