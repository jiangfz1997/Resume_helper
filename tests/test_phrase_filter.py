import uuid

import pytest

from app.models.data_models import (
    Education,
    Skill,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
)
from app.services.phrase_filter import LocalPhraseFilter


@pytest.fixture
def filt() -> LocalPhraseFilter:
    return LocalPhraseFilter()


def _make_draft(
    summary: str = "",
    exp_bullets: list[str] | None = None,
    proj_bullets: list[str] | None = None,
    proj_description: str = "",
) -> TailoredResumeDraft:
    return TailoredResumeDraft(
        summary=summary,
        experiences=[
            TailoredExperience(
                company="Acme",
                title="Engineer",
                start_date="2022-01",
                bullets=[TailoredBullet(text=b) for b in (exp_bullets or [])],
            )
        ],
        education=[
            Education(
                institution="UWO",
                degree="B.Sc",
                field_of_study="CS",
                start_date="2018-09",
            )
        ],
        projects=[
            TailoredProject(
                name="Demo",
                description=proj_description,
                bullets=[TailoredBullet(text=b) for b in (proj_bullets or [])],
            )
        ],
        skills=[Skill(category="Lang", name="Python", proficiency="expert")],
    )


# ── filter_text ────────────────────────────────────────────────


class TestFilterText:
    def test_single_word_replacement(self, filt: LocalPhraseFilter) -> None:
        assert filt.filter_text("We leveraged Docker") == "We used Docker"

    def test_case_insensitive(self, filt: LocalPhraseFilter) -> None:
        assert filt.filter_text("She Spearheaded the project") == "She led the project"

    def test_multi_word_phrase(self, filt: LocalPhraseFilter) -> None:
        assert filt.filter_text("This is cutting-edge technology") == "This is modern technology"

    def test_phrase_replaced_before_component_word(self, filt: LocalPhraseFilter) -> None:
        # "paradigm shift" must match before "paradigm" alone
        result = filt.filter_text("a paradigm shift in the industry")
        assert result == "a change in the industry"

    def test_empty_replacement_collapses_spaces(self, filt: LocalPhraseFilter) -> None:
        result = filt.filter_text("moving forward we will improve")
        assert "  " not in result
        assert result == "we will improve"

    def test_no_partial_word_match(self, filt: LocalPhraseFilter) -> None:
        # "robust" should not match inside "robustness"
        result = filt.filter_text("system robustness is key")
        assert result == "system robustness is key"

    def test_no_match_returns_original(self, filt: LocalPhraseFilter) -> None:
        text = "Built a REST API with FastAPI and PostgreSQL"
        assert filt.filter_text(text) == text

    def test_multiple_replacements_in_one_string(self, filt: LocalPhraseFilter) -> None:
        result = filt.filter_text("orchestrated and leveraged the platform")
        assert "orchestrated" not in result
        assert "leveraged" not in result

    def test_extra_replacements_are_applied(self) -> None:
        filt = LocalPhraseFilter(extra_replacements={"rockstar": "engineer"})
        assert filt.filter_text("Hired a rockstar developer") == "Hired a engineer developer"


# ── process (TailoredResumeDraft) ─────────────────────────────


class TestProcessDraft:
    def test_summary_is_filtered(self, filt: LocalPhraseFilter) -> None:
        draft = _make_draft(summary="I spearheaded the migration utilizing Docker")
        result = filt.process(draft)
        assert "spearheaded" not in result.summary
        assert "utilizing" not in result.summary

    def test_experience_bullets_are_filtered(self, filt: LocalPhraseFilter) -> None:
        draft = _make_draft(exp_bullets=["Leveraged Kubernetes to orchestrate deployments"])
        result = filt.process(draft)
        bullet = result.experiences[0].bullets[0].text
        assert "Leveraged" not in bullet
        assert "orchestrate" not in bullet

    def test_project_description_is_filtered(self, filt: LocalPhraseFilter) -> None:
        draft = _make_draft(proj_description="A cutting-edge solution for data pipelines")
        result = filt.process(draft)
        assert "cutting-edge" not in result.projects[0].description

    def test_project_bullets_are_filtered(self, filt: LocalPhraseFilter) -> None:
        draft = _make_draft(proj_bullets=["Utilized React to build a robust dashboard"])
        result = filt.process(draft)
        bullet = result.projects[0].bullets[0].text
        assert "Utilized" not in bullet
        assert "robust" not in bullet

    def test_structural_fields_are_not_modified(self, filt: LocalPhraseFilter) -> None:
        draft = _make_draft()
        result = filt.process(draft)
        assert result.experiences[0].company == "Acme"
        assert result.experiences[0].start_date == "2022-01"
        assert result.education[0].institution == "UWO"
        assert result.skills[0].name == "Python"

    def test_original_draft_is_not_mutated(self, filt: LocalPhraseFilter) -> None:
        original_summary = "I leveraged Python to spearhead the project"
        draft = _make_draft(summary=original_summary)
        filt.process(draft)
        assert draft.summary == original_summary

    def test_template_metadata_is_preserved(self, filt: LocalPhraseFilter) -> None:
        tid = uuid.uuid4()
        draft = _make_draft(summary="Used Python")
        draft = draft.model_copy(update={"template_id": tid, "template_source": "global"})
        result = filt.process(draft)
        assert result.template_id == tid
        assert result.template_source == "global"
