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
        qualifications=[],
        tech_required=[],
        tech_preferred=[],
        nice_to_have=[],
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
        jd = _make_jd(tech_required=["Python", "FastAPI"])
        draft = _make_draft(summary="Built APIs with Python and FastAPI")
        result = scorer.score(draft, jd)
        assert result.score == 1.0
        assert result.tech_required.matched == 2
        assert result.tech_required.missing == []

    def test_no_match_score_is_zero(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["Kubernetes", "Terraform"])
        draft = _make_draft(summary="Worked on web development with Python")
        result = scorer.score(draft, jd)
        assert result.score == 0.0
        assert result.tech_required.matched == 0

    def test_keyword_found_in_bullet(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["microservices"])
        draft = _make_draft(bullet_texts=["Designed microservices architecture"])
        result = scorer.score(draft, jd)
        assert result.tech_required.matched == 1

    def test_keyword_found_in_skills(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["Go"])
        draft = _make_draft(skill_names=["Go"])
        result = scorer.score(draft, jd)
        assert result.tech_required.matched == 1

    def test_empty_jd_score_is_zero(self, scorer: KeywordScorer) -> None:
        draft = _make_draft(summary="Experienced engineer")
        result = scorer.score(draft, _make_jd())
        assert result.score == 0.0

    def test_required_missing_weighs_more_than_nice_to_have(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(
            tech_required=["Kubernetes"],  # weight 1.0, missed
            nice_to_have=["Docker"],       # weight 0.2, hit
        )
        draft = _make_draft(summary="Experience with Docker")
        result = scorer.score(draft, jd)
        # weighted: (1.0*0/1 + 0.2*1/1) / (1.0+0.2) = 0.2/1.2 ≈ 0.167
        assert result.score < 0.2
        assert result.tech_required.matched == 0
        assert result.nice_to_have.matched == 1

    def test_required_fully_covered_boosts_score(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(
            tech_required=["Kubernetes"],  # weight 1.0, hit
            nice_to_have=["Terraform"],    # weight 0.2, missed
        )
        draft = _make_draft(summary="Experience with Kubernetes")
        result = scorer.score(draft, jd)
        # weighted: (1.0*1/1 + 0.2*0/1) / (1.0+0.2) = 1.0/1.2 ≈ 0.833
        assert result.score > 0.8
        assert result.tech_required.matched == 1

    def test_missing_keywords_flat_list(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["Python", "AWS"])
        draft = _make_draft(summary="Experienced Python developer")
        result = scorer.score(draft, jd)
        assert "AWS" in result.missing_keywords
        assert "Python" in result.matched_keywords

    def test_deduplication_across_same_category(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["Python", "python", "PYTHON"])
        draft = _make_draft(summary="Python developer")
        result = scorer.score(draft, jd)
        assert result.tech_required.total == 1
        assert result.tech_required.matched == 1

    def test_only_tech_required_score_equals_hit_rate(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(tech_required=["FastAPI", "Docker"])
        draft = _make_draft(summary="Built APIs with FastAPI")
        result = scorer.score(draft, jd)
        assert result.tech_required.matched == 1
        assert result.tech_required.total == 2
        assert result.score == round(1 / 2, 4)

    def test_three_tier_weighted_score(self, scorer: KeywordScorer) -> None:
        jd = _make_jd(
            tech_required=["Python"],   # weight 1.0, hit
            tech_preferred=["Redis"],   # weight 0.6, miss
            nice_to_have=["Kafka"],     # weight 0.2, miss
        )
        draft = _make_draft(summary="Python developer")
        result = scorer.score(draft, jd)
        # (1.0*1 + 0.6*0 + 0.2*0) / (1.0+0.6+0.2) = 1.0/1.8 ≈ 0.556
        assert abs(result.score - round(1.0 / 1.8, 4)) < 0.001
        assert result.tech_required.matched == 1
        assert result.tech_preferred.matched == 0
        assert result.nice_to_have.matched == 0
