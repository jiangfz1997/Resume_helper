import uuid
from abc import ABC, abstractmethod

from app.models.data_models import (
    JobDescription,
    MasterProfile,
    MatchingReport,
    ParsedProfileDraft,
    ProfileUpdate,
    SelectionResult,
    Skill,
    SkillGapSuggestion,
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


class IJDAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, jd_text: str) -> JobDescription: ...


class ISkillMatcher(ABC):
    @abstractmethod
    async def match(self, profile: MasterProfile, jd: JobDescription) -> MatchingReport: ...


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


class IDraftPostProcessor(ABC):
    """Synchronous, stateless transform applied to a TailoredResumeDraft after
    the draft-audit loop completes.  Implementations are chained in sequence by
    the pipeline; each receives the output of the previous step."""

    @abstractmethod
    def process(self, draft: TailoredResumeDraft) -> TailoredResumeDraft: ...


class IExperienceSummarizer(ABC):
    @abstractmethod
    async def summarize(self, draft: ParsedProfileDraft) -> ParsedProfileDraft: ...


class ITopNSelector(ABC):
    @abstractmethod
    async def select(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        total_budget: int,
        min_exp: int,
        min_proj: int,
    ) -> SelectionResult: ...
