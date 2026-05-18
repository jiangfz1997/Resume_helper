import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.batch_verifier import BatchVerifier
from app.agents.diagnostic_analyzer import DiagnosticAnalyzer
from app.agents.micro_validator import MicroValidator
from app.api.dependencies import (
    get_batch_verifier,
    get_current_user_id,
    get_diagnostic_analyzer,
    get_micro_validator,
    get_profile_repo,
)
from app.models.data_models import (
    BatchVerifyRequest,
    BatchVerifyResponse,
    DiagnoseRequest,
    DiagnosticReport,
    MicroValidateRequest,
    MicroValidateResponse,
)
from app.repositories.profile_repository import ProfileRepository
from app.services import tier1_checker
from app.services.keyword_scorer import KeywordScorer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["copilot"])

_scorer = KeywordScorer()


@router.post("/diagnose", response_model=DiagnosticReport)
async def diagnose(
    request: DiagnoseRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    analyzer: Annotated[DiagnosticAnalyzer, Depends(get_diagnostic_analyzer)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> DiagnosticReport:
    """
    Full three-tier diagnostic pass on a resume draft.

    - Tier 1: rule-based field checks (sync, instant)
    - Tier 2/3: LLM-based macro/micro analysis (async, one LLM call)
    - Scoring: KeywordScorer re-evaluated on the submitted draft
    """
    logger.info("copilot:diagnose | user_id=%s", user_id)

    # ── Scoring ─────────────────────────────────────────────────
    score_result = _scorer.score(request.draft, request.jd)
    req = score_result.tech_required

    # ── Tier 1 (rule-based, no LLM) ─────────────────────────────
    tier1_tasks = tier1_checker.run(request.profile, request.draft)
    logger.debug("copilot:diagnose | tier1_tasks=%d", len(tier1_tasks))

    # ── Tier 2 + 3 (LLM) ────────────────────────────────────────
    try:
        llm_tasks = await analyzer.analyze(request.draft, request.jd)
    except Exception as exc:
        logger.error("copilot:diagnose | LLM analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Diagnostic analysis failed: {exc}",
        )

    # Tier 1 tasks are prepended so they appear first in the UI.
    all_tasks = tier1_tasks + llm_tasks

    return DiagnosticReport(
        tasks=all_tasks,
        req_score=round(req.matched / max(req.total, 1), 4),
        kw_score=score_result.score,
        kw_detail=score_result,
    )


@router.post("/micro-validate", response_model=MicroValidateResponse)
async def micro_validate(
    request: MicroValidateRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    validator: Annotated[MicroValidator, Depends(get_micro_validator)],
) -> MicroValidateResponse:
    """
    Single-shot micro-validation: check whether a bullet/sentence satisfies a
    natural-language condition.  Routed to Flash Lite for low latency.
    """
    logger.info("copilot:micro-validate | user_id=%s | condition=%.80s", user_id, request.condition)
    try:
        result = await validator.validate(request)
    except Exception as exc:
        logger.error("copilot:micro-validate | failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Micro-validation failed: {exc}",
        )
    logger.debug("copilot:micro-validate | passed=%s reasoning=%s", result.passed, result.reasoning)
    return result


@router.post("/batch-verify", response_model=BatchVerifyResponse)
async def batch_verify(
    request: BatchVerifyRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    verifier: Annotated[BatchVerifier, Depends(get_batch_verifier)],
) -> BatchVerifyResponse:
    """
    Batch-verify which pending tier2/tier3 diagnostic tasks are resolved by
    the supplied section edits.  Tier1 (rule-based) tasks must not be included.
    """
    logger.info(
        "copilot:batch-verify | user_id=%s | sections=%s | tasks=%d",
        user_id,
        list(request.changed_sections.keys()),
        len(request.tasks),
    )
    try:
        return await verifier.verify(request.changed_sections, request.tasks)
    except Exception as exc:
        logger.error("copilot:batch-verify | failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Batch verification failed: {exc}",
        )
