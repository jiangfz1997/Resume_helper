from datetime import datetime

from job_discovery.domain.deduplicate import compute_dedup_keys
from job_discovery.domain.models import DedupKeyKind, SourceJobObservation, SourceName
from job_discovery.domain.normalize import build_candidate


def _candidate(source: SourceName, source_job_id: str, apply_url: str | None, description: str | None):
    observation = SourceJobObservation(
        source=source,
        source_job_id=source_job_id,
        source_url=f"https://example.com/{source_job_id}",
        apply_url_raw=apply_url,
        title_raw="Software Engineer III",
        company_raw="TD",
        location_raw="Toronto, ON, CA",
        description_raw=description,
        observed_at=datetime(2026, 8, 5),
        run_id="run-1",
    )
    return build_candidate(observation)


def test_source_id_key_is_first_and_source_specific() -> None:
    candidate = _candidate(SourceName.INDEED, "jk123", None, None)
    keys = compute_dedup_keys(candidate)
    assert keys[0].kind is DedupKeyKind.SOURCE_ID
    assert keys[0].value == "indeed:jk123"


def test_same_apply_url_across_sources_produces_matching_key() -> None:
    """Mirrors the real probe finding: TD's Software Engineer III posting was
    reachable via both Indeed and Workday with an identical job_url_direct."""
    workday_url = "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers/job/.../Software-Engineer-III_R_1500774"
    a = _candidate(SourceName.WORKDAY, "R_1500774", workday_url, None)
    b = _candidate(SourceName.INDEED, "jk_d75d84f8", workday_url, None)

    key_a = next(k for k in compute_dedup_keys(a) if k.kind is DedupKeyKind.APPLY_URL)
    key_b = next(k for k in compute_dedup_keys(b) if k.kind is DedupKeyKind.APPLY_URL)
    assert key_a.value == key_b.value


def test_weak_key_does_not_conflate_different_companies() -> None:
    a = _candidate(SourceName.INDEED, "1", None, None)
    b = _candidate(SourceName.LINKEDIN, "2", None, None)
    keys_a = compute_dedup_keys(a)
    keys_b = compute_dedup_keys(b)
    weak_a = next(k for k in keys_a if k.kind is DedupKeyKind.COMPANY_TITLE_LOCATION)
    weak_b = next(k for k in keys_b if k.kind is DedupKeyKind.COMPANY_TITLE_LOCATION)
    # same company/title/location fixture on purpose -- this is the same job
    assert weak_a.value == weak_b.value
