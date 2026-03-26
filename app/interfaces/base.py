import uuid
from abc import ABC, abstractmethod

from app.models.data_models import (
    AuditFeedback,
    DraftResume,
    JobDescription,
    MasterProfile,
    MatchingReport,
    ParsedProfileDraft,
    ProfileUpdate,
    Skill,
    TailoredResumeDraft,
    TemplateCreate,
    TemplateRead,
    UserCreate,
    UserUpdate,
)
from app.models.db_models import UserORM


class IUserRepository(ABC):
    @abstractmethod
    async def create(self, data: UserCreate, hashed_password: str) -> UserORM: ...

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> UserORM | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> UserORM | None: ...

    @abstractmethod
    async def update(self, user_id: uuid.UUID, data: UserUpdate) -> UserORM | None: ...


class IProfileRepository(ABC):
    @abstractmethod
    async def get_profile(self, user_id: uuid.UUID) -> MasterProfile | None: ...

    @abstractmethod
    async def upsert_profile(self, user_id: uuid.UUID, data: ProfileUpdate) -> None: ...

    @abstractmethod
    async def append_profile_data(self, user_id: uuid.UUID, data: ParsedProfileDraft) -> None: ...

    @abstractmethod
    async def append_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None: ...

    @abstractmethod
    async def replace_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None: ...

    @abstractmethod
    async def get_skills(self, user_id: uuid.UUID) -> list[Skill]: ...


class ILatexCompiler(ABC):
    @abstractmethod
    async def compile(self, latex_content: str) -> bytes: ...


class IProfileParser(ABC):
    @abstractmethod
    async def parse(self, raw_text: str) -> ParsedProfileDraft: ...


class IProfileEnricher(ABC):
    @abstractmethod
    async def enrich(self, draft: ParsedProfileDraft) -> ParsedProfileDraft: ...


class ILLMClient(ABC):
    """Legacy interface kept for reference. Use IProfileParser instead."""

    @abstractmethod
    async def parse_resume_pdf(self, text: str) -> ParsedProfileDraft: ...


class IJDAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, jd_text: str) -> JobDescription: ...


class ISkillMatcher(ABC):
    @abstractmethod
    async def match(self, profile: MasterProfile, jd: JobDescription) -> MatchingReport: ...


class IResumeGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        feedback: AuditFeedback | None,
        iteration: int,
        preamble: str | None = None,
        body_example: str | None = None,
    ) -> DraftResume: ...


class IResumeAuditor(ABC):
    @abstractmethod
    async def audit(self, draft: DraftResume, jd: JobDescription, threshold: float) -> AuditFeedback: ...


class IContentAuditor(ABC):
    @abstractmethod
    async def audit(self, draft: TailoredResumeDraft, jd: JobDescription, threshold: float) -> AuditFeedback: ...


class IGlobalTemplateRepository(ABC):
    @abstractmethod
    async def create(self, data: TemplateCreate) -> TemplateRead: ...

    @abstractmethod
    async def list_all(self) -> list[TemplateRead]: ...

    @abstractmethod
    async def get_by_id(self, template_id: uuid.UUID) -> TemplateRead | None: ...

    @abstractmethod
    async def delete(self, template_id: uuid.UUID) -> bool: ...


class IUserTemplateRepository(ABC):
    @abstractmethod
    async def create(self, user_id: uuid.UUID, data: TemplateCreate) -> TemplateRead: ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[TemplateRead]: ...

    @abstractmethod
    async def get_by_id(self, template_id: uuid.UUID) -> TemplateRead | None: ...

    @abstractmethod
    async def delete(self, template_id: uuid.UUID, user_id: uuid.UUID) -> bool: ...
