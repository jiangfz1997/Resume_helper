from __future__ import annotations

import pytest

from job_discovery.domain.seniority import assess_seniority


@pytest.mark.parametrize(
    "title",
    [
        "New Grad Software Engineer",
        "Junior Software Developer",
        "Software Developer Internship/Co-op",
        "Full Stack Developer - Entry Level",
        "Stagiaire en Developpement Cloud",
        "Developpeur(euse) logiciel junior C#",
    ],
)
def test_flags_new_grad_titles(title: str) -> None:
    assert assess_seniority(title, None).is_new_grad is True


@pytest.mark.parametrize(
    "description",
    [
        "We welcome recent graduates to apply.",
        "This is an entry-level opening on our platform team.",
        "No prior experience is required.",
        "Open to graduating students in the 2026 cohort.",
    ],
)
def test_flags_new_grad_descriptions(description: str) -> None:
    assert assess_seniority("Software Engineer", description).is_new_grad is True


@pytest.mark.parametrize(
    "title",
    ["Senior Software Engineer", "Staff Backend Engineer", "Principal Architect", "Engineering Manager"],
)
def test_senior_titles_veto_every_other_signal(title: str) -> None:
    """A senior posting that mentions mentoring juniors, or recruiting from
    campus, is still a senior posting."""
    assessment = assess_seniority(title, "You will mentor junior engineers and support our campus hires.")
    assert assessment.is_new_grad is False
    assert assessment.signals == []


def test_plain_mid_level_posting_is_not_tagged() -> None:
    assert assess_seniority("Software Engineer II", "Build and ship backend services.").is_new_grad is False


def test_signals_name_every_rule_that_fired() -> None:
    assessment = assess_seniority("Junior Developer", "We hire recent graduates every spring.")
    assert assessment.signals == ["junior_title", "new_grad_text"]
