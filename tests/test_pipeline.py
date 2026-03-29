import uuid
from unittest.mock import AsyncMock

import pytest

from app.interfaces.base import IJDAnalyzer, IResumeAuditor, IResumeGenerator, ISkillMatcher
from app.models.data_models import (
    AuditFeedback,
    DraftResume,
    JobDescription,
    MasterProfile,
    MatchingReport,
    PipelineConfig,
    PipelineStatus,
    ResumeRequest,
)
from app.pipeline.pipeline import ResumePipeline
from app.services.profile_manager import ProfileManager

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_SAMPLE_LATEX = r"\documentclass{article}\begin{document}Resume\end{document}"


def _make_profile() -> MasterProfile:
    return MasterProfile(user_id=TEST_USER_ID, full_name="Jane Doe")


def _make_jd() -> JobDescription:
    return JobDescription(title="Backend Engineer", tech_keywords=["Python"])


def _make_report() -> MatchingReport:
    return MatchingReport(matched_skills=["Python"], missing_skills=[], relevance_notes="Good fit")


def _make_draft(iteration: int = 0) -> DraftResume:
    return DraftResume(latex_content=_SAMPLE_LATEX, iteration=iteration)


def _make_pipeline(
    profile: MasterProfile | None,
    jd: JobDescription,
    report: MatchingReport,
    audit_responses: list[AuditFeedback],
) -> ResumePipeline:
    mock_profile_manager = AsyncMock(spec=ProfileManager)
    mock_profile_manager.load_master_profile.return_value = profile

    mock_jd_analyzer = AsyncMock(spec=IJDAnalyzer)
    mock_jd_analyzer.analyze.return_value = jd

    mock_skill_matcher = AsyncMock(spec=ISkillMatcher)
    mock_skill_matcher.match.return_value = report

    draft_counter = {"n": 0}

    async def _generate(*args, iteration=0, **kwargs) -> DraftResume:
        return _make_draft(iteration=kwargs.get("iteration", draft_counter["n"]))

    mock_generator = AsyncMock(spec=IResumeGenerator)
    mock_generator.generate.side_effect = lambda **kw: _make_draft(iteration=kw.get("iteration", 0))

    mock_auditor = AsyncMock(spec=IResumeAuditor)
    mock_auditor.audit.side_effect = audit_responses

    return ResumePipeline(
        profile_manager=mock_profile_manager,
        jd_analyzer=mock_jd_analyzer,
        skill_matcher=mock_skill_matcher,
        resume_generator=mock_generator,
        resume_auditor=mock_auditor,
    )


@pytest.mark.asyncio
async def test_pipeline_approved_on_first_try():
    feedback = AuditFeedback(score=0.9, suggestions=[], approved=True)
    pipeline = _make_pipeline(_make_profile(), _make_jd(), _make_report(), [feedback])

    request = ResumeRequest(jd_text="Sample JD")
    result = await pipeline.run(TEST_USER_ID, request)

    assert result.status == PipelineStatus.approved
    assert result.score == 0.9
    assert result.retries == 1


@pytest.mark.asyncio
async def test_pipeline_approved_after_retry():
    feedback_fail = AuditFeedback(score=0.6, suggestions=["Add Docker"], approved=False)
    feedback_pass = AuditFeedback(score=0.85, suggestions=[], approved=True)
    pipeline = _make_pipeline(
        _make_profile(), _make_jd(), _make_report(), [feedback_fail, feedback_pass]
    )

    request = ResumeRequest(jd_text="Sample JD")
    result = await pipeline.run(TEST_USER_ID, request)

    assert result.status == PipelineStatus.approved
    assert result.score == 0.85
    assert result.retries == 2


@pytest.mark.asyncio
async def test_pipeline_max_retries_returns_best_draft():
    feedbacks = [
        AuditFeedback(score=0.5, suggestions=["Fix A"], approved=False),
        AuditFeedback(score=0.7, suggestions=["Fix B"], approved=False),
        AuditFeedback(score=0.6, suggestions=["Fix C"], approved=False),
    ]
    config = PipelineConfig(max_retries=3, initial_threshold=0.8)
    pipeline = _make_pipeline(_make_profile(), _make_jd(), _make_report(), feedbacks)

    request = ResumeRequest(jd_text="Sample JD", config=config)
    result = await pipeline.run(TEST_USER_ID, request)

    assert result.status == PipelineStatus.max_retries_reached
    assert result.score == 0.7


@pytest.mark.asyncio
async def test_pipeline_raises_when_profile_not_found():
    pipeline = _make_pipeline(None, _make_jd(), _make_report(), [])

    request = ResumeRequest(jd_text="Sample JD")
    with pytest.raises(Exception):
        await pipeline.run(TEST_USER_ID, request)


@pytest.mark.asyncio
async def test_pipeline_threshold_decays_across_retries():
    captured_thresholds: list[float] = []

    async def _audit_side_effect(draft, jd, threshold):
        captured_thresholds.append(threshold)
        return AuditFeedback(score=0.5, suggestions=[], approved=False)

    mock_profile_manager = AsyncMock(spec=ProfileManager)
    mock_profile_manager.load_master_profile.return_value = _make_profile()

    mock_jd_analyzer = AsyncMock(spec=IJDAnalyzer)
    mock_jd_analyzer.analyze.return_value = _make_jd()

    mock_skill_matcher = AsyncMock(spec=ISkillMatcher)
    mock_skill_matcher.match.return_value = _make_report()

    mock_generator = AsyncMock(spec=IResumeGenerator)
    mock_generator.generate.return_value = _make_draft()

    mock_auditor = AsyncMock(spec=IResumeAuditor)
    mock_auditor.audit.side_effect = _audit_side_effect

    config = PipelineConfig(
        initial_threshold=0.8,
        decay_per_retry=0.1,
        min_threshold=0.6,
        max_retries=3,
    )
    pipeline = ResumePipeline(
        profile_manager=mock_profile_manager,
        jd_analyzer=mock_jd_analyzer,
        skill_matcher=mock_skill_matcher,
        resume_generator=mock_generator,
        resume_auditor=mock_auditor,
    )

    await pipeline.run(TEST_USER_ID, ResumeRequest(jd_text="Sample JD", config=config))

    assert captured_thresholds[0] == pytest.approx(0.8)
    assert captured_thresholds[1] == pytest.approx(0.7)
    assert captured_thresholds[2] == pytest.approx(0.6)
