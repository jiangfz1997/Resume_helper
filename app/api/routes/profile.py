import io
import logging
import uuid
from typing import Annotated

import fitz  # pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_current_user_id,
    get_profile_chat_agent,
    get_profile_parse_pipeline,
    get_profile_repo,
)
from app.agents.profile_chat_agent import OllamaProfileChatAgent
from app.models.data_models import MasterProfile, MockProfileInjectRequest, ParsedProfileDraft, ProfileChatRequest, ProfileUpdate, SkillsAppend
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.repositories.profile_repository import ProfileRepository
from app.services.profile_manager import ProfileManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF using pymupdf block-level extraction.

    Each text block (paragraph / bullet) in the PDF is emitted as a single
    line, so visually-wrapped long bullets are not split across lines.
    Blocks are sorted by vertical then horizontal position to preserve
    reading order across single- and two-column layouts.
    """
    doc = fitz.open(stream=content, filetype="pdf")
    result_lines: list[str] = []
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 5) * 5, b[0]))
        for block in blocks:
            text: str = block[4]
            for line in text.splitlines():
                cleaned = " ".join(line.split())
                if cleaned:
                    result_lines.append(cleaned)
    return "\n".join(result_lines)


def _get_profile_manager(
    repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> ProfileManager:
    return ProfileManager(repo)


@router.get("/", response_model=MasterProfile)
async def get_profile(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    logger.debug("get_profile | user_id=%s", user_id)
    profile = await manager.load_master_profile(user_id)
    if profile is None:
        logger.warning("get_profile | not found | user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    logger.debug("get_profile | success | skills=%d experiences=%d", len(profile.skills), len(profile.work_experiences))
    return profile


@router.put("/", response_model=MasterProfile)
async def update_profile(
    data: ProfileUpdate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    logger.debug("update_profile | user_id=%s", user_id)
    await manager.save_profile(user_id, data)
    profile = await manager.load_master_profile(user_id)
    if profile is None:
        logger.warning("update_profile | not found after upsert | user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    logger.info("update_profile | success | user_id=%s", user_id)
    return profile


@router.put("/skills", response_model=MasterProfile)
async def replace_skills(
    data: SkillsAppend,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    logger.debug("replace_skills | user_id=%s count=%d", user_id, len(data.skills))
    await manager.replace_skills(user_id, data.skills)
    profile = await manager.load_master_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/skills", response_model=MasterProfile)
async def append_skills(
    data: SkillsAppend,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    logger.debug("append_skills | user_id=%s count=%d", user_id, len(data.skills))
    await manager.append_skills(user_id, data.skills)
    profile = await manager.load_master_profile(user_id)
    if profile is None:
        logger.warning("append_skills | not found | user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    logger.info("append_skills | success | user_id=%s total_skills=%d", user_id, len(profile.skills))
    return profile



@router.post("/chat/stream")
async def stream_profile_chat(
    request: ProfileChatRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    agent: Annotated[OllamaProfileChatAgent, Depends(get_profile_chat_agent)],
) -> StreamingResponse:
    logger.info(
        "stream_profile_chat | user_id=%s section=%s index=%s",
        user_id, request.section_type, request.section_index,
    )

    async def event_stream():
        async for event in agent.stream_chat(request):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/upload-pdf", response_model=ParsedProfileDraft)
async def upload_resume_pdf(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    pipeline: Annotated[ProfileParsePipeline, Depends(get_profile_parse_pipeline)],
    file: UploadFile = File(...),
) -> ParsedProfileDraft:
    logger.debug("upload_pdf | user_id=%s filename=%s", user_id, file.filename)
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a PDF"
        )
    content = await file.read()
    text = _extract_pdf_text(content)
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract text from PDF",
        )
    logger.debug("upload_pdf | extracted %d chars | running parse pipeline", len(text))
    try:
        result = await pipeline.run(text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    logger.info(
        "upload_pdf | success | user_id=%s skills=%d experiences=%d projects=%d",
        user_id, len(result.skills), len(result.work_experiences), len(result.projects),
    )
    return result


@router.post("/upload-pdf/confirm", response_model=MasterProfile)
async def confirm_parsed_draft(
    draft: ParsedProfileDraft,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    logger.debug(
        "confirm_draft | user_id=%s skills=%d experiences=%d projects=%d",
        user_id, len(draft.skills), len(draft.work_experiences), len(draft.projects),
    )
    for i, p in enumerate(draft.projects):
        logger.debug("confirm_draft | project[%d] name=%s bullets=%d", i, p.name, len(p.bullets))
    profile = await manager.replace_parsed_draft(user_id, draft)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    logger.info("confirm_draft | success | user_id=%s", user_id)
    return profile


def _parse_time_range(time_str: str) -> tuple[str, str | None]:
    from app.agents.profile_enricher import _normalize_date
    parts = [p.strip() for p in time_str.split(" - ", 1)]
    start = _normalize_date(parts[0]) or "" if parts else ""
    end: str | None = None
    if len(parts) > 1 and parts[1].lower() not in ("present", "now", "current", ""):
        end = _normalize_date(parts[1])
    return start, end


@router.post("/inject-mock", response_model=MasterProfile)
async def inject_mock_profile(
    request: MockProfileInjectRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    manager: Annotated[ProfileManager, Depends(_get_profile_manager)],
) -> MasterProfile:
    from app.models.data_models import Project, WorkExperience
    from app.agents.profile_enricher import CodeProfileEnricher

    work_experiences: list[WorkExperience] = []
    for w in request.works:
        start, end = _parse_time_range(w.time)
        work_experiences.append(WorkExperience(
            title=w.name,
            company=w.location or "—",
            start_date=start,
            end_date=end,
            description=w.experiences,
        ))

    projects: list[Project] = []
    for p in request.projects:
        projects.append(Project(
            name=p.name,
            description=p.experiences[0] if p.experiences else p.name,
            bullets=p.experiences,
        ))

    from app.agents.experience_summarizer import ExperienceSummarizer

    draft = ParsedProfileDraft(work_experiences=work_experiences, projects=projects)
    enriched = await CodeProfileEnricher().enrich(draft)
    summarized = await ExperienceSummarizer().summarize(enriched)

    profile = await manager.append_parsed_draft(user_id, summarized)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    logger.info(
        "inject_mock | user_id=%s | works=%d projects=%d skills=%d",
        user_id, len(summarized.work_experiences), len(summarized.projects), len(summarized.skills),
    )
    return profile
