import pytest

from app.models.data_models import (
    Education,
    JobDescription,
    Skill,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
)
from app.services.keyword_scorer import KeywordScorer, _keyword_in_text


def _make_jd(**kwargs) -> JobDescription:
    defaults = dict(
        title="Software Engineer",
        hard_requirements=[],
        core_keywords=[],
        soft_skills=[],
        preferred_qualifications=[],
    )
    return JobDescription(**{**defaults, **kwargs})


def _make_draft(
    summary: str = "",
    bullet_texts: list[str] | None = None,
    skill_names: list[str] | None = None,
) -> TailoredResumeDraft:
    return TailoredResumeDraft(
        summary=summary,
        experiences=[
            TailoredExperience(
                company="Acme",
                title="Engineer",
                start_date="2022-01",
                bullets=[TailoredBullet(text=t) for t in (bullet_texts or [])],
            )
        ],
        education=[
            Education(institution="UWO", degree="B.Sc", field_of_study="CS", start_date="2019-09")
        ],
        projects=[TailoredProject(name="Demo", description="")],
        skills=[Skill(category="Lang", name=n, proficiency="expert") for n in (skill_names or [])],
    )


# ── _keyword_in_text ───────────────────────────────────────────


class TestKeywordInText:
    def test_exact_match(self) -> None:
        assert _keyword_in_text("python", "used python for scripting")

    def test_case_insensitive(self) -> None:
        assert _keyword_in_text("Python", "experienced with PYTHON")

    def test_no_partial_match(self) -> None:
        assert not _keyword_in_text("go", "going forward with golang")

    def test_multi_word_keyword(self) -> None:
        assert _keyword_in_text("machine learning", "applied machine learning techniques")

    def test_not_found(self) -> None:
        assert not _keyword_in_text("kubernetes", "deployed with docker")


# ── KeywordScorer.score ────────────────────────────────────────


class TestKeywordScorer:
    @pytest.fixture
    def scorer(self) -> KeywordScorer:
        return KeywordScorer()

    def test_full_match_score_is_one(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(hard_requirements=["Python", "FastAPI"])
        draft = _make_draft(summary="Built APIs with Python and FastAPI")
        result = scorer.score(draft, jd)
        assert result.score == 1.0
        assert result.hard_requirements.matched == 2
        assert result.hard_requirements.missing == []

    def test_no_match_score_is_zero(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(hard_requirements=["Kubernetes", "Terraform"])
        draft = _make_draft(summary="Worked on web development with Python")
        result = scorer.score(draft, jd)
        assert result.score == 0.0
        assert result.hard_requirements.matched == 0

    def test_keyword_found_in_bullet(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(core_keywords=["microservices"])
        draft = _make_draft(bullet_texts=["Designed microservices architecture"])
        result = scorer.score(draft, jd)
        assert result.core_keywords.matched == 1

    def test_keyword_found_in_skills(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(core_keywords=["Go"])
        draft = _make_draft(skill_names=["Go"])
        result = scorer.score(draft, jd)
        assert result.core_keywords.matched == 1

    def test_empty_jd_score_is_zero(self, scorer: KeywordScorer) -> None:
        draft = _make_draft(summary="Experienced engineer")
        result = scorer.score(draft, _make_jd())
        assert result.score == 0.0

    def test_required_missing_weighs_more_than_preferred(self, scorer: KeywordScorer) -> None:
        # Draft hits preferred but not required — score should be low
        jd = _make_jd(
            hard_requirements=["Kubernetes"],      # weight 1.0, missed
            preferred_qualifications=["Docker"],   # weight 0.5, hit
        )
        draft = _make_draft(summary="Experience with Docker")
        result = scorer.score(draft, jd)
        # weighted: (1.0 * 0/1 + 0.5 * 1/1) / (1.0 + 0.5) = 0.5/1.5 ≈ 0.333
        assert result.score < 0.4
        assert result.hard_requirements.matched == 0
        assert result.preferred_qualifications.matched == 1

    def test_required_fully_covered_boosts_score(self, scorer: KeywordScorer) -> None:
        # Draft hits required but not preferred — score should still be high
        jd = _make_jd(
            hard_requirements=["Kubernetes"],      # weight 1.0, hit
            preferred_qualifications=["Terraform"],  # weight 0.5, missed
        )
        draft = _make_draft(summary="Experience with Kubernetes")
        result = scorer.score(draft, jd)
        # weighted: (1.0 * 1/1 + 0.5 * 0/1) / (1.0 + 0.5) = 1.0/1.5 ≈ 0.667
        assert result.score > 0.6
        assert result.hard_requirements.matched == 1

    def test_missing_keywords_flat_list(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(hard_requirements=["Python", "AWS"])
        draft = _make_draft(summary="Experienced Python developer")
        result = scorer.score(draft, jd)
        assert "AWS" in result.missing_keywords
        assert "Python" in result.matched_keywords

    def test_deduplication_across_same_category(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(hard_requirements=["Python", "python", "PYTHON"])
        draft = _make_draft(summary="Python developer")
        result = scorer.score(draft, jd)
        assert result.hard_requirements.total == 1
        assert result.hard_requirements.matched == 1

    def test_category_with_no_keywords_excluded_from_weight(self, scorer: KeywordScorer) -> None:
        # Only hard_requirements present — score should be pure hard_requirements rate
        jd = _make_jd(hard_requirements=["FastAPI", "Docker"])
        draft = _make_draft(summary="Built APIs with FastAPI")
        result = scorer.score(draft, jd)
        assert result.hard_requirements.matched == 1
        assert result.hard_requirements.total == 2
        assert result.score == round(1 / 2, 4)
