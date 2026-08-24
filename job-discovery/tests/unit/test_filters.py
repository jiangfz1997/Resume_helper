from datetime import datetime

from job_discovery.domain.filters import FilterConfig, apply_hard_filters, classify_category
from job_discovery.domain.models import EligibilityStatus, FilterCode, JobCategory, SourceJobObservation, SourceName
from job_discovery.domain.normalize import build_candidate

CONFIG = FilterConfig(filter_version="v1", min_description_chars=300)


def _candidate(title: str, description_chars: int, location: str = "Toronto, ON, CA"):
    observation = SourceJobObservation(
        source=SourceName.LINKEDIN,
        source_job_id="1",
        source_url="https://linkedin.com/jobs/view/1",
        title_raw=title,
        company_raw="Acme",
        location_raw=location,
        description_raw=("x" * description_chars) if description_chars else None,
        observed_at=datetime(2026, 8, 5),
        run_id="run-1",
    )
    return build_candidate(observation)


def test_short_description_is_review_not_excluded() -> None:
    """Real case from the LinkedIn probe: a 170-char description came back
    for an otherwise normal posting. It should be held for review, not
    dropped -- and must not silently trigger a browser fallback."""
    decision = apply_hard_filters(_candidate("Backend Developer", 170), CONFIG)
    assert decision.status is EligibilityStatus.REVIEW
    assert FilterCode.DESCRIPTION_TOO_SHORT in decision.codes


def test_missing_description_is_review() -> None:
    decision = apply_hard_filters(_candidate("Backend Developer", 0), CONFIG)
    assert decision.status is EligibilityStatus.REVIEW
    assert FilterCode.DESCRIPTION_MISSING in decision.codes


def test_excluded_title_wins_over_review_title() -> None:
    decision = apply_hard_filters(_candidate("Staff / Principal Software Engineer", 500), CONFIG)
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.EXCLUDED_TITLE in decision.codes


def test_senior_title_is_review() -> None:
    decision = apply_hard_filters(_candidate("Senior Software Engineer", 500), CONFIG)
    assert decision.status is EligibilityStatus.REVIEW
    assert FilterCode.REVIEW_TITLE in decision.codes


def test_clean_posting_is_eligible() -> None:
    decision = apply_hard_filters(_candidate("Software Engineer", 500), CONFIG)
    assert decision.status is EligibilityStatus.ELIGIBLE
    assert decision.codes == []


def test_location_mismatch_is_excluded() -> None:
    config = FilterConfig(filter_version="v1", accepted_locations=["Toronto"], min_description_chars=0)
    decision = apply_hard_filters(_candidate("Software Engineer", 10, location="Vancouver, BC, CA"), config)
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.LOCATION_MISMATCH in decision.codes


def test_remote_bypasses_location_filter() -> None:
    config = FilterConfig(filter_version="v1", accepted_locations=["Toronto"], min_description_chars=0)
    decision = apply_hard_filters(_candidate("Software Engineer", 10, location="Remote"), config)
    assert FilterCode.LOCATION_MISMATCH not in decision.codes


def test_irrelevant_title_is_excluded() -> None:
    """Real case from a live run: a CNC Machinist posting only got excluded
    by chance because its location didn't match. Location and seniority
    checks alone let any job category through -- this is the actual
    relevance gate."""
    decision = apply_hard_filters(_candidate("CNC Machinist/Programmer", 500), CONFIG)
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.TITLE_NOT_RELEVANT in decision.codes


def test_qa_title_is_relevant() -> None:
    decision = apply_hard_filters(_candidate("QA Engineer", 500), CONFIG)
    assert FilterCode.TITLE_NOT_RELEVANT not in decision.codes


def test_empty_include_list_disables_the_relevance_check() -> None:
    config = FilterConfig(filter_version="v1", include_title_keywords=[], min_description_chars=0)
    decision = apply_hard_filters(_candidate("CNC Machinist/Programmer", 500), config)
    assert FilterCode.TITLE_NOT_RELEVANT not in decision.codes


def test_classify_category_tags_sde_titles() -> None:
    assert classify_category("backend developer") is JobCategory.SDE
    assert classify_category("senior software engineer") is JobCategory.SDE


def test_classify_category_tags_qa_titles() -> None:
    assert classify_category("qa engineer") is JobCategory.QA
    assert classify_category("sdet") is JobCategory.QA


def test_classify_category_is_none_for_unrelated_titles() -> None:
    assert classify_category("cnc machinist/programmer") is None


YEARS_CONFIG = FilterConfig(filter_version="v1", min_description_chars=0, max_required_years=3)


def _years_candidate(title: str, description: str):
    return build_candidate(
        SourceJobObservation(
            source=SourceName.LINKEDIN,
            source_job_id="1",
            source_url="https://linkedin.com/jobs/view/1",
            title_raw=title,
            company_raw="Acme",
            location_raw="Toronto, ON, CA",
            description_raw=description,
            observed_at=datetime(2026, 8, 5),
            run_id="run-1",
        )
    )


def test_posting_above_the_threshold_is_excluded() -> None:
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "We need 8+ years of experience."), YEARS_CONFIG
    )
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.YEARS_TOO_HIGH in decision.codes


def test_posting_at_the_threshold_is_eligible() -> None:
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "We need 3 years of experience."), YEARS_CONFIG
    )
    assert decision.status is EligibilityStatus.ELIGIBLE


def test_range_above_the_threshold_is_excluded_by_its_upper_bound() -> None:
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "We need 3-5 years of experience."), YEARS_CONFIG
    )
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.YEARS_TOO_HIGH in decision.codes


def test_new_grad_tag_does_not_rescue_a_stated_bar() -> None:
    """A "Junior" title over a description demanding five years is a real
    pattern in the corpus. The parsed number wins -- otherwise the tag becomes
    a hole straight through the filter this whole feature exists to provide."""
    decision = apply_hard_filters(
        _years_candidate("Junior Software Developer", "You bring 5+ years of experience."), YEARS_CONFIG
    )
    assert decision.status is EligibilityStatus.EXCLUDED
    assert FilterCode.YEARS_TOO_HIGH in decision.codes


def test_new_grad_tag_rescues_an_unparsed_mention() -> None:
    """Internships and co-ops rarely state a number; 10 of the 15 genuine
    new-grad postings in the live table have none. Without the tag they would
    all sit in manual review."""
    decision = apply_hard_filters(
        _years_candidate(
            "Software Developer Internship/Co-op",
            "Open to recent graduates. Several years of experience is not expected.",
        ),
        YEARS_CONFIG,
    )
    assert decision.status is EligibilityStatus.ELIGIBLE


def test_unparsed_mention_without_a_new_grad_signal_is_review() -> None:
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "You bring several years of experience to the team."),
        YEARS_CONFIG,
    )
    assert decision.status is EligibilityStatus.REVIEW
    assert FilterCode.YEARS_UNPARSED in decision.codes


def test_posting_stating_no_requirement_is_not_reviewed() -> None:
    """Most postings simply omit the bar. Flagging all of them would bury the
    genuinely ambiguous ones."""
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "Build and ship backend services with a great team."),
        YEARS_CONFIG,
    )
    assert decision.status is EligibilityStatus.ELIGIBLE


def test_threshold_unset_disables_the_gate_entirely() -> None:
    decision = apply_hard_filters(
        _years_candidate("Backend Developer", "We need 12+ years of experience."),
        FilterConfig(filter_version="v1", min_description_chars=0),
    )
    assert decision.status is EligibilityStatus.ELIGIBLE
