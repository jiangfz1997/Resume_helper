import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.experience_summarizer import ExperienceSummarizer
from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.agents.profile_chat_agent import OllamaProfileChatAgent
from app.agents.profile_enricher import CodeProfileEnricher
from app.agents.profile_parser import TwoPhaseProfileParser
from app.agents.resume_chat_agent import OllamaResumeChatAgent
from app.agents.skill_matcher import OllamaSkillMatcher
from app.agents.top_n_selector import TopNSelector
from app.core.database import get_session
from app.pipeline.pipeline import ResumePipeline
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.services.latex_compiler import TectonicCompiler
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
        top_n_selector=TopNSelector(),
    )


def get_latex_compiler() -> TectonicCompiler:
    return TectonicCompiler()


def get_profile_parse_pipeline() -> ProfileParsePipeline:
    return ProfileParsePipeline(
        parser=TwoPhaseProfileParser(),
        enricher=CodeProfileEnricher(),
        summarizer=ExperienceSummarizer(),
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


async def get_chat_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatRepository:
    return ChatRepository(session)


def get_chat_agent() -> OllamaResumeChatAgent:
    return OllamaResumeChatAgent()


def get_profile_chat_agent() -> OllamaProfileChatAgent:
    return OllamaProfileChatAgent()


def get_diagnostic_analyzer():
    from app.agents.diagnostic_analyzer import DiagnosticAnalyzer
    return DiagnosticAnalyzer()


def get_micro_validator():
    from app.agents.micro_validator import MicroValidator
    return MicroValidator()


def get_batch_verifier():
    from app.agents.batch_verifier import BatchVerifier
    return BatchVerifier()


async def get_current_admin_id(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> uuid.UUID:
    from app.core.config import settings

    user = await user_repo.get_by_id(user_id)
    if user is None or user.email not in settings.admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user_id
