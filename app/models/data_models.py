import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator, model_validator


class CategoryMatchResult(BaseModel):
    total: int
    matched: int
    missing: list[str]


class QualificationResult(BaseModel):
    item: str
    matched: bool
    reason: str


class KeywordMatchResult(BaseModel):
    score: float                          # weighted composite (tech_required × 1.0 + tech_preferred × 0.6 + nice_to_have × 0.2)
    tech_required: CategoryMatchResult
    tech_preferred: CategoryMatchResult
    nice_to_have: CategoryMatchResult
    matched_keywords: list[str]
    missing_keywords: list[str]

    @computed_field
    @property
    def tech_keywords(self) -> CategoryMatchResult:
        return self.tech_required

    @computed_field
    @property
    def preferred_qualifications(self) -> CategoryMatchResult:
        return self.nice_to_have


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


class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None


class WorkExperience(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: Optional[str] = None
    description: list[str] = Field(default_factory=list)
    ai_summary: Optional[str] = None
    ai_keywords: list[str] = Field(default_factory=list)
    ai_implied_keywords: list[str] = Field(default_factory=list)

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
    ai_summary: Optional[str] = None
    ai_keywords: list[str] = Field(default_factory=list)
    ai_implied_keywords: list[str] = Field(default_factory=list)


_PROFICIENCY_ALIASES: dict[str, ProficiencyLevel] = {
    "advanced": ProficiencyLevel.expert,
    "proficient": ProficiencyLevel.intermediate,
    "basic": ProficiencyLevel.beginner,
    "novice": ProficiencyLevel.beginner,
    "familiar": ProficiencyLevel.beginner,
    "not specified": ProficiencyLevel.beginner,
    "unknown": ProficiencyLevel.beginner,
    "n/a": ProficiencyLevel.beginner,
}


class Skill(BaseModel):
    category: str
    name: str
    proficiency: Optional[ProficiencyLevel] = None


class ProfileUpdate(BaseModel):
    work_experiences: Optional[list[WorkExperience]] = None
    educations: Optional[list[Education]] = None
    projects: Optional[list[Project]] = None
    summary: Optional[str] = None
    contact_info: Optional[ContactInfo] = None


class SkillsAppend(BaseModel):
    skills: list[Skill]


class MasterProfile(BaseModel):
    user_id: uuid.UUID
    full_name: str
    summary: Optional[str] = None
    contact_info: Optional[ContactInfo] = None
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)


class UnclassifiedSection(BaseModel):
    """A resume section that matched none of the four supported categories.

    Surfaced to the user on the import confirmation screen so that content is never
    dropped silently. Not persisted: it carries no meaning once the user has decided
    what to do with it.
    """

    title: str
    content: list[str] = Field(default_factory=list)


class ParsedProfileDraft(BaseModel):
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    summary: Optional[str] = None
    unclassified_sections: list[UnclassifiedSection] = Field(default_factory=list)


class JobDescription(BaseModel):
    title: str
    company: Optional[str] = None
    qualifications: list[str] = Field(default_factory=list)
    tech_required: list[str] = Field(default_factory=list)
    tech_preferred: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "tech_keywords" in data and "tech_required" not in data:
            data["tech_required"] = data.pop("tech_keywords", [])
        if "preferred_qualifications" in data and "tech_preferred" not in data:
            data["nice_to_have"] = data.pop("preferred_qualifications", [])
            data.setdefault("tech_preferred", [])
        return data

    @computed_field
    @property
    def tech_keywords(self) -> list[str]:
        return self.tech_required + self.tech_preferred

    @computed_field
    @property
    def preferred_qualifications(self) -> list[str]:
        return self.nice_to_have


class TechCoverageItem(BaseModel):
    keyword: str
    matched: bool
    matched_via: Optional[str] = None
    reason: str


class MatchingReport(BaseModel):
    """Skill match for one session.

    Every ``*_indices`` field here and on the request models below indexes
    ``ResumeSessionORM.profile_snapshot_json``, never the live profile. The
    snapshot is frozen when the session is created, which is what keeps the
    positions valid after the user edits or reorders their profile. Resolve them
    against the snapshot only.
    """

    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    highlighted_experience_indices: list[int] = Field(default_factory=list)
    highlighted_project_indices: list[int] = Field(default_factory=list)
    topn_experience_indices: list[int] = Field(default_factory=list)
    topn_project_indices: list[int] = Field(default_factory=list)
    relevance_notes: str = ""
    qualification_details: list[QualificationResult] = Field(default_factory=list)
    tech_coverage: list[TechCoverageItem] = Field(default_factory=list)



class PipelineConfig(BaseModel):
    initial_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    decay_per_retry: float = Field(default=0.05, ge=0.0)
    min_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_retries: int = Field(default=1, ge=1)



class CompileRequest(BaseModel):
    latex_content: str


class ResumeAnalyzeRequest(BaseModel):
    jd_text: str


class MockEntry(BaseModel):
    name: str
    time: str = ""
    location: str = ""
    experiences: list[str] = Field(default_factory=list)


class MockProfileInjectRequest(BaseModel):
    projects: list[MockEntry] = Field(default_factory=list)
    works: list[MockEntry] = Field(default_factory=list)


class SelectionResult(BaseModel):
    selected_experience_indices: list[int] = Field(default_factory=list)
    selected_project_indices: list[int] = Field(default_factory=list)


class SkillGapSuggestion(BaseModel):
    missing_keyword: str
    covered_by: list[str]  # names of unselected experiences/projects that contain this keyword


class MatchingPreview(BaseModel):
    session_id: str
    match_score: float = Field(ge=0.0, le=1.0)
    job_title: str
    company: Optional[str] = None
    matched_skills: list[str]
    missing_skills: list[str]
    highlighted_experience_indices: list[int] = Field(default_factory=list)
    highlighted_project_indices: list[int] = Field(default_factory=list)
    topn_experience_indices: list[int] = Field(default_factory=list)
    topn_project_indices: list[int] = Field(default_factory=list)
    all_experiences: list[WorkExperience]
    all_projects: list[Project]
    relevance_notes: str
    qualification_details: list[QualificationResult] = Field(default_factory=list)
    kw_detail: Optional[KeywordMatchResult] = None
    skill_gap_suggestions: list["SkillGapSuggestion"] = Field(default_factory=list)


class GenerateConfirmRequest(BaseModel):
    session_id: str
    config: PipelineConfig = Field(default_factory=PipelineConfig)
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None
    selected_experience_indices: Optional[list[int]] = None
    selected_project_indices: Optional[list[int]] = None


class TailorOneRequest(BaseModel):
    session_id: str
    item_type: Literal["exp", "proj"]
    item_index: int


class TailorFullRequest(BaseModel):
    session_id: str
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None
    selected_experience_indices: Optional[list[int]] = None
    selected_project_indices: Optional[list[int]] = None


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


class CustomSection(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


class TailoredResumeDraft(BaseModel):
    summary: str = ""
    experiences: list[TailoredExperience]
    education: list[Education]
    projects: list[TailoredProject]
    skills: list[Skill]
    contact_info: Optional[ContactInfo] = None
    show_summary: bool = True
    show_experiences: bool = True
    show_education: bool = True
    show_projects: bool = True
    show_skills: bool = True
    custom_sections: list[CustomSection] = Field(default_factory=list)
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None


class RenderRequest(BaseModel):
    draft: TailoredResumeDraft
    template_id: Optional[uuid.UUID] = None
    template_source: Optional[Literal["global", "user"]] = None
    compile: bool = True


class LayoutSettings(BaseModel):
    font_family: str = "Georgia"
    font_size: int = Field(default=3, ge=1, le=5)
    section_gap: int = Field(default=3, ge=1, le=5)
    item_gap: int = Field(default=3, ge=1, le=5)
    line_height: int = Field(default=3, ge=1, le=5)
    margin_h: int = Field(default=15, ge=8, le=25)
    margin_v: int = Field(default=15, ge=8, le=25)
    compact_mode: bool = False
    accent_color: str = "#1a1a1a"


class HtmlPreviewRequest(BaseModel):
    draft: TailoredResumeDraft
    settings: LayoutSettings = Field(default_factory=LayoutSettings)
    full_name: str = ""


class PdfExportRequest(BaseModel):
    draft: TailoredResumeDraft
    settings: LayoutSettings = Field(default_factory=LayoutSettings)
    full_name: str = ""


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
    jd: Optional["JobDescription"] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    match_score: Optional[float] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    highlighted_experience_indices: list[int] = Field(default_factory=list)
    highlighted_project_indices: list[int] = Field(default_factory=list)
    all_experiences: list["WorkExperience"] = Field(default_factory=list)
    all_projects: list["Project"] = Field(default_factory=list)
    relevance_notes: str = ""
    qualification_details: list["QualificationResult"] = Field(default_factory=list)
    status: ResumeSessionStatus
    tailored_draft: Optional["TailoredResumeDraft"] = None
    kw_detail: Optional["KeywordMatchResult"] = None
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
    previous_value: Optional[Any] = None
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



# ── copilot / diagnostic models ────────────────────────────────

class DiagnosticTier(str, Enum):
    tier1 = "tier1"  # rule-based: missing required fields
    tier2 = "tier2"  # LLM macro: keyword gaps, missing quantification
    tier3 = "tier3"  # LLM micro: weak verbs, unstructured phrasing


class DiagnosticTask(BaseModel):
    id: str = Field(description="Stable unique key used by frontend to track completion state")
    tier: DiagnosticTier
    title: str = Field(description="Short label rendered as card header")
    description: str = Field(description="Full suggestion text shown in expanded card")
    # Navigation target — used by Tier 1/2 'go to edit' button
    section: Optional[str] = Field(
        default=None,
        description="Draft path to focus when user clicks the action button, e.g. 'experiences[0]'",
    )
    action_label: Optional[str] = Field(
        default=None,
        description="Label on the action button, e.g. 'Go to Edit'",
    )
    # Zero-based index of the bullet within the item (experiences[n] or projects[n]).
    # Used by the frontend to highlight the specific bullet in the preview iframe.
    bullet_index: Optional[int] = Field(
        default=None,
        description="Zero-based bullet index within the section item, for preview highlighting",
    )
    # Tier 3 one-click replacement
    replaceable: bool = Field(
        default=False,
        description="Whether the frontend can apply a one-click text replacement",
    )
    original_text: Optional[str] = Field(
        default=None,
        description="Tier 3: exact text to be replaced in the draft",
    )
    suggested_text: Optional[str] = Field(
        default=None,
        description="Tier 3: replacement text proposed by the LLM",
    )
    # Micro-validation support
    verify_condition: Optional[str] = Field(
        default=None,
        description="Natural-language condition sent to micro-validator, e.g. 'contains a concurrency metric'",
    )


class DiagnosticReport(BaseModel):
    tasks: list[DiagnosticTask] = Field(default_factory=list)
    req_score: float = Field(ge=0.0, le=1.0, description="Hard-requirements coverage (0–1)")
    kw_score: float = Field(ge=0.0, le=1.0, description="Keyword coverage excluding hard requirements (0–1)")
    kw_detail: Optional["KeywordMatchResult"] = Field(default=None, description="Per-category keyword breakdown")


class DiagnoseRequest(BaseModel):
    draft: TailoredResumeDraft
    jd: JobDescription
    profile: MasterProfile


class BatchVerifyRequest(BaseModel):
    changed_sections: dict[str, str] = Field(
        description="Map of section path (e.g. 'experiences[0]') to current text content"
    )
    tasks: list[DiagnosticTask] = Field(
        description="Pending tier2/tier3 tasks to check against the changed content"
    )


class BatchVerifyResult(BaseModel):
    id: str
    reason: str


class BatchVerifyResponse(BaseModel):
    resolved: list[BatchVerifyResult] = Field(default_factory=list)
    jd: JobDescription
    profile: MasterProfile


class MicroValidateRequest(BaseModel):
    text: str = Field(description="The bullet or sentence to evaluate")
    condition: str = Field(description="Natural-language condition to check, e.g. 'contains a concurrency metric'")


class MicroValidateResponse(BaseModel):
    passed: bool
    reasoning: str = Field(default="", description="One-sentence explanation returned by the model")


# ── template models ─────────────────────────────────────────────

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
