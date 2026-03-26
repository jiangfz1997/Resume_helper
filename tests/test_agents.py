import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.agents.resume_auditor import OllamaResumeAuditor
from app.agents.resume_generator import OllamaResumeGenerator
from app.agents.skill_matcher import OllamaSkillMatcher
from app.models.data_models import (
    AuditFeedback,
    DraftResume,
    Education,
    JobDescription,
    MasterProfile,
    MatchingReport,
    Skill,
    ProficiencyLevel,
    WorkExperience,
)


def _make_agent_without_init(cls: type) -> object:
    instance = cls.__new__(cls)
    mock_chain = AsyncMock()
    instance._chain = mock_chain
    return instance, mock_chain


def _make_profile() -> MasterProfile:
    return MasterProfile(
        user_id=uuid.uuid4(),
        full_name="Jane Doe",
        summary="Backend engineer",
        work_experiences=[
            WorkExperience(
                company="Acme",
                title="Senior Engineer",
                start_date="2020-01",
                description=["Built REST APIs", "Led team of 4"],
            )
        ],
        educations=[
            Education(
                institution="UWO",
                degree="BSc",
                field_of_study="Computer Science",
                start_date="2016-09",
                end_date="2020-04",
            )
        ],
        skills=[Skill(category="Languages", name="Python", proficiency=ProficiencyLevel.expert)],
    )


@pytest.mark.asyncio
async def test_jd_analyzer_returns_job_description():
    analyzer, mock_chain = _make_agent_without_init(OllamaJDAnalyzer)
    mock_chain.ainvoke.return_value = {
        "title": "Backend Engineer",
        "company": "TechCorp",
        "hard_requirements": ["Python", "FastAPI"],
        "core_keywords": ["REST", "async"],
        "soft_skills": ["communication"],
        "preferred_qualifications": ["Docker"],
    }

    result = await analyzer.analyze("Sample JD text")

    assert isinstance(result, JobDescription)
    assert result.title == "Backend Engineer"
    assert "Python" in result.hard_requirements
    mock_chain.ainvoke.assert_called_once_with({"jd_text": "Sample JD text"})


@pytest.mark.asyncio
async def test_skill_matcher_returns_matching_report():
    matcher, mock_chain = _make_agent_without_init(OllamaSkillMatcher)
    mock_chain.ainvoke.return_value = {
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": ["Kubernetes"],
        "highlighted_experiences": ["Built REST APIs at Acme"],
        "relevance_notes": "Strong backend match, missing infra skills.",
    }

    profile = _make_profile()
    jd = JobDescription(title="Backend Engineer", hard_requirements=["Python"])

    result = await matcher.match(profile, jd)

    assert isinstance(result, MatchingReport)
    assert "Python" in result.matched_skills
    assert "Kubernetes" in result.missing_skills


@pytest.mark.asyncio
async def test_resume_generator_returns_draft():
    generator, mock_chain = _make_agent_without_init(OllamaResumeGenerator)
    mock_chain.ainvoke.return_value = r"\documentclass{article}\begin{document}CV\end{document}"

    profile = _make_profile()
    jd = JobDescription(title="Backend Engineer")
    report = MatchingReport(matched_skills=["Python"])

    result = await generator.generate(
        profile=profile, jd=jd, matching_report=report, feedback=None, iteration=0
    )

    assert isinstance(result, DraftResume)
    assert result.latex_content.startswith(r"\documentclass")
    assert result.iteration == 0


@pytest.mark.asyncio
async def test_resume_generator_includes_feedback_section():
    generator, mock_chain = _make_agent_without_init(OllamaResumeGenerator)
    mock_chain.ainvoke.return_value = r"\documentclass{article}\begin{document}CV v2\end{document}"

    profile = _make_profile()
    jd = JobDescription(title="Backend Engineer")
    report = MatchingReport()
    feedback = AuditFeedback(score=0.65, suggestions=["Add Docker skills"], approved=False)

    await generator.generate(
        profile=profile, jd=jd, matching_report=report, feedback=feedback, iteration=1
    )

    call_kwargs = mock_chain.ainvoke.call_args[0][0]
    assert "Add Docker skills" in call_kwargs["audit_feedback_section"]


@pytest.mark.asyncio
async def test_resume_auditor_approved_when_score_above_threshold():
    auditor, mock_chain = _make_agent_without_init(OllamaResumeAuditor)
    mock_chain.ainvoke.return_value = {
        "score": 0.9,
        "suggestions": [],
        "approved": False,
    }

    draft = DraftResume(latex_content=r"\documentclass{article}\begin{document}\end{document}")
    jd = JobDescription(title="Backend Engineer")

    result = await auditor.audit(draft, jd, threshold=0.8)

    assert isinstance(result, AuditFeedback)
    assert result.score == 0.9
    assert result.approved is True


@pytest.mark.asyncio
async def test_resume_auditor_not_approved_when_score_below_threshold():
    auditor, mock_chain = _make_agent_without_init(OllamaResumeAuditor)
    mock_chain.ainvoke.return_value = {
        "score": 0.5,
        "suggestions": ["Add more keywords"],
        "approved": True,
    }

    draft = DraftResume(latex_content=r"\documentclass{article}\begin{document}\end{document}")
    jd = JobDescription(title="Backend Engineer")

    result = await auditor.audit(draft, jd, threshold=0.8)

    assert result.score == 0.5
    assert result.approved is False
