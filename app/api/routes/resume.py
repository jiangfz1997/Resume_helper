import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.dependencies import (
    get_current_user_id,
    get_global_template_repo,
    get_latex_compiler,
    get_pipeline,
    get_profile_repo,
    get_session_repo,
    get_tailor_pipeline,
    get_user_template_repo,
    get_v2_pipeline,
)
from app.pipeline.tailor_pipeline import TailorPipeline
from app.pipeline.v2_pipeline import V2ResumePipeline
from app.repositories.profile_repository import ProfileRepository
from app.services.profile_manager import ProfileManager
from app.repositories.template_repository import GlobalTemplateRepository, UserTemplateRepository
from app.models.data_models import (
    CompileRequest,
    GenerateConfirmRequest,
    MatchingPreview,
    RenderRequest,
    ResumeAnalyzeRequest,
    ResumeRequest,
    ResumeResponse,
    TailoredResumeDraft,
)
from app.pipeline.pipeline import ResumePipeline
from app.repositories.session_repository import ResumeSessionRepository
from app.services.latex_compiler import LatexCompilationError, TectonicCompiler
from app.services.template_filler import TemplateFiller, build_jinja2_template

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resume", tags=["resume"])

_DEFAULT_TEMPLATE = (
    Path(__file__).parent.parent.parent / "latex_templates" / "classic.tex.j2"
).read_text(encoding="utf-8")


@router.post("/analyze", response_model=MatchingPreview)
async def analyze_jd(
    request: ResumeAnalyzeRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    pipeline: Annotated[ResumePipeline, Depends(get_pipeline)],
    session_repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
) -> MatchingPreview:
    logger.info("analyze_jd | user_id=%s | jd_len=%d", user_id, len(request.jd_text))
    db_session = await session_repo.create(user_id, request.jd_text)
    try:
        result = await pipeline.analyze_and_preview(user_id, request)
        await session_repo.update_after_analysis(
            db_session.id, result.profile, result.jd, result.matching_report, result.preview.match_score
        )
        preview = result.preview.model_copy(update={"session_id": str(db_session.id)})
        logger.info(
            "analyze_jd | done | user_id=%s | session_id=%s | match_score=%.2f",
            user_id, preview.session_id, preview.match_score,
        )
        return preview
    except Exception as exc:
        await session_repo.mark_failed(db_session.id, str(exc))
        logger.warning("analyze_jd | error | user_id=%s | %s", user_id, exc)
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        raise


@router.post("/confirm", response_model=TailoredResumeDraft)
async def confirm_and_draft(
    request: GenerateConfirmRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    v2: Annotated[V2ResumePipeline, Depends(get_v2_pipeline)],
    tailor: Annotated[TailorPipeline, Depends(get_tailor_pipeline)],
    session_repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    global_repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
    user_repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> TailoredResumeDraft:
    logger.info(
        "confirm_and_draft | user_id=%s | session_id=%s | template_id=%s",
        user_id, request.session_id, request.template_id,
    )

    db_session = await session_repo.get(uuid.UUID(request.session_id), user_id)
    if db_session is None or db_session.profile_snapshot_json is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired")

    from app.models.data_models import JobDescription, MasterProfile, MatchingReport
    profile = MasterProfile.model_validate(db_session.profile_snapshot_json)
    jd = JobDescription.model_validate(db_session.jd_json)
    matching_report = MatchingReport.model_validate(db_session.matching_report_json)

    if request.selected_experience_indices is not None:
        filtered_exp = [
            profile.work_experiences[i]
            for i in request.selected_experience_indices
            if 0 <= i < len(profile.work_experiences)
        ]
        profile = profile.model_copy(update={"work_experiences": filtered_exp})
    if request.selected_project_indices is not None:
        filtered_proj = [
            profile.projects[i]
            for i in request.selected_project_indices
            if 0 <= i < len(profile.projects)
        ]
        profile = profile.model_copy(update={"projects": filtered_proj})

    jinja2_template: str = _DEFAULT_TEMPLATE
    template_id = request.template_id
    template_source = request.template_source

    if template_id is not None:
        if template_source == "global":
            tpl = await global_repo.get_by_id(template_id)
        else:
            tpl = await user_repo.get_by_id(template_id)
        if tpl is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        jinja2_template = build_jinja2_template(tpl.preamble, template_source or "user")

    await session_repo.mark_generating(
        uuid.UUID(request.session_id),
        request.selected_experience_indices,
        request.selected_project_indices,
        template_id,
        template_source,
        request.config,
    )

    current_profile = await ProfileManager(profile_repo).load_master_profile(user_id)
    use_tailor = current_profile is not None and current_profile.base_resume is not None

    try:
        if use_tailor:
            logger.info("confirm_and_draft | using TailorPipeline (base_resume found) | user_id=%s", user_id)
            base_resume = current_profile.base_resume.model_copy(update={  # type: ignore[union-attr]
                "template_id": template_id,
                "template_source": template_source,
            })
            draft, _, _ = await tailor.run(
                profile=profile,
                base_resume=base_resume,
                jd_text=db_session.jd_text,
            )
        else:
            logger.info("confirm_and_draft | using V2Pipeline (no base_resume) | user_id=%s", user_id)
            draft = await v2.run(
                profile=profile,
                jd=jd,
                matching_report=matching_report,
                config=request.config,
                template_id=template_id,
                template_source=template_source,
            )
        await session_repo.update_draft(uuid.UUID(request.session_id), draft)
        logger.info("confirm_and_draft | done | user_id=%s | pipeline=%s", user_id, "tailor" if use_tailor else "v2")
        return draft
    except Exception as exc:
        await session_repo.mark_failed(uuid.UUID(request.session_id), str(exc))
        raise


@router.post(
    "/render",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Compiled PDF"},
        200: {"content": {"text/plain": {}}, "description": "LaTeX source"},
        422: {"description": "LaTeX compilation error"},
        503: {"description": "tectonic not available"},
    },
)
async def render_draft(
    request: RenderRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    compiler: Annotated[TectonicCompiler, Depends(get_latex_compiler)],
    global_repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
    user_repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> Response:
    template_id = request.template_id or request.draft.template_id
    template_source = request.template_source or request.draft.template_source

    jinja2_content: str | None = None
    if template_id is not None:
        if template_source == "global":
            tpl = await global_repo.get_by_id(template_id)
        else:
            tpl = await user_repo.get_by_id(template_id)
        if tpl is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        jinja2_content = build_jinja2_template(tpl.preamble, template_source or "user")
    else:
        jinja2_content = _DEFAULT_TEMPLATE

    try:
        latex_content = TemplateFiller(jinja2_content).render(request.draft)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Template render error: {exc}")

    if not request.compile:
        return Response(content=latex_content, media_type="text/plain")

    logger.info("render_draft | user_id=%s | latex_len=%d compile=True", user_id, len(latex_content))
    logger.debug("render_draft | latex_preview=\n%s", latex_content[:3000])
    try:
        pdf_bytes = await compiler.compile(latex_content)
        logger.info("render_draft | done | user_id=%s | pdf_bytes=%d", user_id, len(pdf_bytes))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=resume.pdf"},
        )
    except LatexCompilationError as exc:
        msg = str(exc)
        logger.error("render_draft | compile failed | latex=\n%s", latex_content)
        if "not installed" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.post(
    "/compile",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Compiled PDF"},
        422: {"description": "LaTeX compilation error"},
        503: {"description": "tectonic not available"},
    },
)
async def compile_latex(
    request: CompileRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    compiler: Annotated[TectonicCompiler, Depends(get_latex_compiler)],
) -> Response:
    logger.info("compile_latex | user_id=%s | latex_len=%d", user_id, len(request.latex_content))
    try:
        pdf_bytes = await compiler.compile(request.latex_content)
        logger.info("compile_latex | done | user_id=%s | pdf_bytes=%d", user_id, len(pdf_bytes))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=resume.pdf"},
        )
    except LatexCompilationError as exc:
        msg = str(exc)
        if "not installed" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.post("/generate", response_model=ResumeResponse)
async def generate_resume(
    request: ResumeRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    pipeline: Annotated[ResumePipeline, Depends(get_pipeline)],
) -> ResumeResponse:
    logger.info(
        "generate_resume | user_id=%s | jd_len=%d | max_retries=%d threshold=%.2f",
        user_id, len(request.jd_text), request.config.max_retries, request.config.initial_threshold,
    )
    try:
        result = await pipeline.run(user_id, request)
        logger.info(
            "generate_resume | done | user_id=%s | status=%s score=%.2f retries=%d",
            user_id, result.status, result.score, result.retries,
        )
        return result
    except ValueError as exc:
        logger.warning("generate_resume | error | user_id=%s | %s", user_id, exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
