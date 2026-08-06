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
