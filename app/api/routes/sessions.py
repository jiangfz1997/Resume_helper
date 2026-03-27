import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user_id, get_session_repo
from app.models.data_models import (
    DraftUpdateRequest,
    JobDescription,
    MatchingPreview,
    MasterProfile,
    MatchingReport,
    ResumeSessionDetail,
    ResumeSessionStatus,
    ResumeSessionSummary,
    TailoredResumeDraft,
)
from app.models.db_models import ResumeSessionORM
from app.repositories.session_repository import ResumeSessionRepository
from app.services.keyword_scorer import KeywordScorer

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_summary(row: ResumeSessionORM) -> ResumeSessionSummary:
    return ResumeSessionSummary(
        id=str(row.id),
        job_title=row.job_title,
        company=row.company,
        match_score=row.match_score,
        status=ResumeSessionStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_detail(row: ResumeSessionORM) -> ResumeSessionDetail:
    matching_preview: MatchingPreview | None = None
    if row.matching_report_json and row.profile_snapshot_json:
        report = MatchingReport.model_validate(row.matching_report_json)
        profile = MasterProfile.model_validate(row.profile_snapshot_json)
        matched = report.matched_skills
        missing = report.missing_skills
        all_exp = profile.work_experiences
        all_proj = profile.projects
        highlighted = report.highlighted_experiences
        relevance = report.relevance_notes
    else:
        matched, missing, all_exp, all_proj, highlighted, relevance = [], [], [], [], [], ""

    tailored_draft: TailoredResumeDraft | None = None
    keyword_coverage = 0.0
    required_coverage = 0.0
    if row.tailored_draft_json:
        tailored_draft = TailoredResumeDraft.model_validate(row.tailored_draft_json)
        if row.jd_json:
            jd = JobDescription.model_validate(row.jd_json)
            kw = KeywordScorer().score(tailored_draft, jd)
            req = kw.hard_requirements
            keyword_coverage = kw.score
            required_coverage = round(req.matched / req.total, 4) if req.total else 0.0

    return ResumeSessionDetail(
        id=str(row.id),
        jd_text=row.jd_text,
        job_title=row.job_title,
        company=row.company,
        match_score=row.match_score,
        matched_skills=matched,
        missing_skills=missing,
        highlighted_experiences=highlighted,
        all_experiences=all_exp,
        all_projects=all_proj,
        relevance_notes=relevance,
        status=ResumeSessionStatus(row.status),
        tailored_draft=tailored_draft,
        keyword_coverage=keyword_coverage,
        required_coverage=required_coverage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ResumeSessionSummary])
async def list_sessions(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
    limit: int = 20,
    offset: int = 0,
) -> list[ResumeSessionSummary]:
    rows = await repo.list_by_user(user_id, limit=limit, offset=offset)
    return [_to_summary(r) for r in rows]


@router.get("/{session_id}", response_model=ResumeSessionDetail)
async def get_session(
    session_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
) -> ResumeSessionDetail:
    row = await repo.get(session_id, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return _to_detail(row)


@router.patch("/{session_id}/draft", response_model=ResumeSessionSummary)
async def update_draft(
    session_id: uuid.UUID,
    request: DraftUpdateRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
) -> ResumeSessionSummary:
    row = await repo.get(session_id, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await repo.update_draft(session_id, request.tailored_draft)
    updated = await repo.get(session_id, user_id)
    return _to_summary(updated)  # type: ignore[arg-type]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
) -> None:
    deleted = await repo.delete(session_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
