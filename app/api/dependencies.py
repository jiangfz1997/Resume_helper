import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.services.latex_compiler import TectonicCompiler
from app.agents.profile_enricher import CodeProfileEnricher
from app.agents.profile_parser import TwoPhaseProfileParser
from app.agents.resume_auditor import OllamaResumeAuditor
from app.agents.content_auditor import OllamaContentAuditor
from app.agents.resume_generator import OllamaResumeGenerator
from app.agents.skill_matcher import OllamaSkillMatcher
from app.core.database import get_session
from app.pipeline.pipeline import ResumePipeline
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.pipeline.tailor_pipeline import TailorPipeline
from app.pipeline.v2_pipeline import V2ResumePipeline
from app.agents.base_resume_builder import OllamaBaseResumeBuilder
from app.agents.content_drafter import OllamaContentDrafter
from app.agents.resume_tailor import OllamaResumeTailor
from app.agents.resume_chat_agent import OllamaResumeChatAgent
from app.agents.profile_chat_agent import OllamaProfileChatAgent
from app.repositories.chat_repository import ChatRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.session_repository import ResumeSessionRepository
from app.repositories.template_repository import GlobalTemplateRepository, UserTemplateRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.profile_manager import ProfileManager
from app.services.template_filler import TemplateFiller

_bearer = HTTPBearer()


async def get_user_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_profile_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileRepository:
    return ProfileRepository(session)


async def get_auth_service(
    repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> AuthService:
    return AuthService(repo)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> uuid.UUID:
    user_id_str = auth_service.decode_token(credentials.credentials)
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return uuid.UUID(user_id_str)


async def get_pipeline(
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> ResumePipeline:
    return ResumePipeline(
        profile_manager=ProfileManager(profile_repo),
        jd_analyzer=OllamaJDAnalyzer(),
        skill_matcher=OllamaSkillMatcher(),
        resume_generator=OllamaResumeGenerator(),
        resume_auditor=OllamaResumeAuditor(),
    )


def get_latex_compiler() -> TectonicCompiler:
    return TectonicCompiler()


def get_profile_parse_pipeline() -> ProfileParsePipeline:
    return ProfileParsePipeline(
        parser=TwoPhaseProfileParser(),
        enricher=CodeProfileEnricher(),
    )


async def get_session_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResumeSessionRepository:
    return ResumeSessionRepository(session)


async def get_global_template_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GlobalTemplateRepository:
    return GlobalTemplateRepository(session)


async def get_user_template_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserTemplateRepository:
    return UserTemplateRepository(session)


def get_content_drafter() -> OllamaContentDrafter:
    return OllamaContentDrafter()


def get_v2_pipeline() -> V2ResumePipeline:
    return V2ResumePipeline(
        drafter=OllamaContentDrafter(),
        auditor=OllamaContentAuditor(),
    )


def get_tailor_pipeline() -> TailorPipeline:
    return TailorPipeline(
        jd_analyzer=OllamaJDAnalyzer(),
        skill_matcher=OllamaSkillMatcher(),
        tailor=OllamaResumeTailor(),
    )


def get_base_resume_builder() -> OllamaBaseResumeBuilder:
    return OllamaBaseResumeBuilder()


async def get_chat_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatRepository:
    return ChatRepository(session)


def get_chat_agent() -> OllamaResumeChatAgent:
    return OllamaResumeChatAgent()


def get_profile_chat_agent() -> OllamaProfileChatAgent:
    return OllamaProfileChatAgent()


async def get_current_admin_id(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> uuid.UUID:
    from app.core.config import settings

    user = await user_repo.get_by_id(user_id)
    if user is None or user.email not in settings.admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user_id
