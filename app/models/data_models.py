import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ProficiencyLevel(str, Enum):
    expert = "expert"
    intermediate = "intermediate"
    beginner = "beginner"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WorkExperience(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: Optional[str] = None
    description: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            for f in ("company", "title", "start_date"):
                if data.get(f) is None:
                    data[f] = ""
        return data


class Education(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: Optional[str] = None
    gpa: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            for f in ("institution", "degree", "field_of_study", "start_date"):
                if data.get(f) is None:
                    data[f] = ""
        return data


class Project(BaseModel):
    name: str
    description: str
    bullets: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    url: Optional[str] = None


_PROFICIENCY_ALIASES: dict[str, ProficiencyLevel] = {
    "advanced": ProficiencyLevel.expert,
    "proficient": ProficiencyLevel.intermediate,
    "basic": ProficiencyLevel.beginner,
    "novice": ProficiencyLevel.beginner,
    "familiar": ProficiencyLevel.beginner,
}


class Skill(BaseModel):
    category: str
    name: str
    proficiency: ProficiencyLevel

    @field_validator("proficiency", mode="before")
    @classmethod
    def _normalize_proficiency(cls, v: object) -> object:
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in _PROFICIENCY_ALIASES:
                return _PROFICIENCY_ALIASES[normalized]
            return normalized
        return v


class ProfileUpdate(BaseModel):
    work_experiences: Optional[list[WorkExperience]] = None
    educations: Optional[list[Education]] = None
    projects: Optional[list[Project]] = None
    summary: Optional[str] = None


class SkillsAppend(BaseModel):
    skills: list[Skill]


class MasterProfile(BaseModel):
    user_id: uuid.UUID
    full_name: str
    summary: Optional[str] = None
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    base_resume: Optional["TailoredResumeDraft"] = None


class ParsedProfileDraft(BaseModel):
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    summary: Optional[str] = None


class JobDescription(BaseModel):
    title: str
    company: Optional[str] = None
    hard_requirements: list[str] = Field(default_factory=list)
    core_keywords: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)


class MatchingReport(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    highlighted_experiences: list[str] = Field(default_factory=list)
    relevance_notes: str = ""


class AuditFeedback(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    suggestions: list[str] = Field(default_factory=list)
    approved: bool


class DraftResume(BaseModel):
    latex_content: str
    iteration: int = 0


class PipelineStatus(str, Enum):
    in_progress = "in_progress"
    approved = "approved"
    max_retries_reached = "max_retries_reached"


class PipelineConfig(BaseModel):
    initial_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    decay_per_retry: float = Field(default=0.05, ge=0.0)
    min_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=1)


class PipelineState(BaseModel):
    retry_count: int = 0
    best_score: float = 0.0
    best_draft: Optional[DraftResume] = None
    status: PipelineStatus = PipelineStatus.in_progress


class CompileRequest(BaseModel):
    latex_content: str


class ResumeAnalyzeRequest(BaseModel):
    jd_text: str


class MatchingPreview(BaseModel):
    session_id: str
    match_score: float = Field(ge=0.0, le=1.0)
    job_title: str
    company: Optional[str] = None
    matched_skills: list[str]
    missing_skills: list[str]
    highlighted_experiences: list[str]
    all_experiences: list[WorkExperience]
    all_projects: list[Project]
    relevance_notes: str


class GenerateConfirmRequest(BaseModel):
    session_id: str
    selected_experience_indices: Optional[list[int]] = None
    selected_project_indices: Optional[list[int]] = None
    config: PipelineConfig = Field(default_factory=PipelineConfig)
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None


class ResumeRequest(BaseModel):
    jd_text: str
    config: PipelineConfig = Field(default_factory=PipelineConfig)


class ResumeResponse(BaseModel):
    latex_content: str
    score: float
    retries: int
    status: PipelineStatus


# ── v2 models ──────────────────────────────────────────

class TailoredBullet(BaseModel):
    text: str
    highlighted: bool = False


class TailoredExperience(BaseModel):
    company: str
    title: str
    location: str = ""
    start_date: str
    end_date: Optional[str] = None
    bullets: list[TailoredBullet]


class TailoredProject(BaseModel):
    name: str
    description: str
    tech_stack: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    bullets: list[TailoredBullet] = Field(default_factory=list)


class TailoredResumeDraft(BaseModel):
    summary: str
    experiences: list[TailoredExperience]
    education: list[Education]
    projects: list[TailoredProject]
    skills: list[Skill]
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None


class RenderRequest(BaseModel):
    draft: TailoredResumeDraft
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None
    compile: bool = True


class ResumeSessionStatus(str, Enum):
    analyzing = "analyzing"
    analyzed = "analyzed"
    generating = "generating"
    draft_ready = "draft_ready"
    failed = "failed"


class ResumeSessionSummary(BaseModel):
    id: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    match_score: Optional[float] = None
    status: ResumeSessionStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeSessionDetail(BaseModel):
    id: str
    jd_text: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    match_score: Optional[float] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    highlighted_experiences: list[str] = Field(default_factory=list)
    all_experiences: list["WorkExperience"] = Field(default_factory=list)
    all_projects: list["Project"] = Field(default_factory=list)
    relevance_notes: str = ""
    status: ResumeSessionStatus
    tailored_draft: Optional["TailoredResumeDraft"] = None
    created_at: datetime
    updated_at: datetime


class DraftUpdateRequest(BaseModel):
    tailored_draft: "TailoredResumeDraft"


# ── chat models ────────────────────────────────────────

class ChatScope(BaseModel):
    path: str    # "summary" | "experiences[0]" | "projects[1]"
    label: str   # human-readable label shown in the UI


class ResumePatch(BaseModel):
    path: str
    updated_value: Any   # str for summary, TailoredExperience / TailoredProject otherwise
    diff_summary: str


class ChatMessage(BaseModel):
    id: Optional[uuid.UUID] = None
    role: Literal["user", "assistant"]
    content: str
    scope: Optional[ChatScope] = None
    patch: Optional[ResumePatch] = None
    created_at: Optional[datetime] = None


class ResumeChatRequest(BaseModel):
    session_id: uuid.UUID
    draft: TailoredResumeDraft
    message: str
    scope: Optional[ChatScope] = None
    history: list[ChatMessage] = Field(default_factory=list)


class ResumeChatResponse(BaseModel):
    message: ChatMessage
    patch: Optional[ResumePatch] = None


class ProfileChatRequest(BaseModel):
    section_type: str
    section_index: Optional[int] = None
    section_data: Any
    scope: Optional[ChatScope] = None
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    industry: Optional[str] = Field(default=None, max_length=80)
    style_tag: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = None
    preamble: str = Field(min_length=1)
    body_example: Optional[str] = None


class TemplateRead(BaseModel):
    id: uuid.UUID
    name: str
    industry: Optional[str] = None
    style_tag: Optional[str] = None
    description: Optional[str] = None
    preamble: str
    body_example: Optional[str] = None
    created_at: datetime
    source: Literal["global", "user"]

    model_config = {"from_attributes": True}
