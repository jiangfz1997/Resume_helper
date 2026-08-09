from __future__ import annotations

import pytest

from job_discovery.domain.years import MAX_PLAUSIBLE_YEARS, extract_years


@pytest.mark.parametrize(
    "text,minimum,maximum",
    [
        ("We want 5+ years of experience.", 5, None),
        ("3-5 years of relevant experience required.", 3, 5),
        ("2 to 4 years of experience.", 2, 4),
        ("Minimum of 7 years of hands-on experience.", 7, None),
        ("At least five years of experience in QA.", 5, None),
        ("3 or more years of experience with Python.", 3, None),
        ("Five (5) years of progressive experience.", 5, None),
        ("8 years experience or more in backend systems.", 8, None),
    ],
)
def test_parses_common_phrasings(text: str, minimum: int, maximum: int | None) -> None:
    result = extract_years(text)
    assert (result.minimum, result.maximum) == (minimum, maximum)


@pytest.mark.parametrize(
    "text,minimum,maximum",
    [
        (r"We want 8\+ years of experience.", 8, None),
        (r"3\-5 years of experience required.", 3, 5),
        (r"Five (5\) years of experience.", 5, None),
    ],
)
def test_parses_markdown_escaped_forms(text: str, minimum: int, maximum: int | None) -> None:
    """jobspy's markdown converter escapes "+" and "-", so live rows read
    "8\\+ years". Tolerating the backslash is worth roughly 30 points of
    coverage on the real corpus -- these cases are the majority of postings,
    not an edge case."""
    result = extract_years(text)
    assert (result.minimum, result.maximum) == (minimum, maximum)


def test_range_does_not_also_yield_its_own_upper_bound() -> None:
    """Without overlap suppression "3-5 years" produces a second bare hit at
    "5 years" and the binding minimum reads as 5 instead of 3."""
    result = extract_years("Looking for 3-5 years of experience.")
    assert result.minimum == 3
    assert [hit.snippet for hit in result.hits] == ["3-5 years"]


def test_takes_the_highest_binding_requirement() -> None:
    result = extract_years(
        "You have 7+ years of backend experience. You also have 4+ years of experience with Python."
    )
    assert result.minimum == 7


def test_maximum_pairs_with_the_hit_that_set_the_minimum() -> None:
    result = extract_years(
        "Ideally 2-3 years of experience with React. Requires 7+ years of overall engineering experience."
    )
    assert (result.minimum, result.maximum) == (7, None)


def test_preferred_requirements_lose_to_required_ones() -> None:
    result = extract_years(
        "Required: 2 years of experience. Preferred qualifications: 10 years of experience would be a plus."
    )
    assert result.minimum == 2


def test_preferred_only_still_reports_a_number() -> None:
    result = extract_years("Nice-to-have: 6 years of experience with Kubernetes is desirable.")
    assert result.minimum == 6
    assert result.hits[0].preferred is True


def test_ignores_company_tenure_prose() -> None:
    result = extract_years("For over 30 years we have delivered excellence. No experience bar is listed.")
    assert result.minimum is None


def test_ignores_durations_unrelated_to_experience() -> None:
    result = extract_years("This is a 2 year fixed-term contract with a competitive salary.")
    assert result.minimum is None


def test_rejects_implausibly_large_numbers() -> None:
    result = extract_years(f"We require {MAX_PLAUSIBLE_YEARS + 25} years of experience.")
    assert result.minimum is None


def test_distinguishes_unparsed_mention_from_silence() -> None:
    silent = extract_years("A great role for a motivated engineer.")
    assert silent.mentioned is False
    assert silent.unparsed_mention is False

    vague = extract_years("Candidates should bring several years of experience.")
    assert vague.minimum is None
    assert vague.unparsed_mention is True


def test_empty_description_is_not_a_mention() -> None:
    assert extract_years(None).mentioned is False
    assert extract_years("").mentioned is False
