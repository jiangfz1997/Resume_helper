from datetime import datetime

from job_discovery.domain.models import PostedAtQuality, SourceJobObservation, SourceName, WorkplaceType
from job_discovery.domain.normalize import build_candidate, normalize_url, parse_posted_at


def test_normalize_url_is_idempotent() -> None:
    raw = "HTTPS://Example.com/Job/123/?utm_source=indeed&ref=abc&gh_jid=999#apply"
    once = normalize_url(raw)
    twice = normalize_url(once)
    assert once == twice


def test_normalize_url_strips_tracking_params_but_keeps_others() -> None:
    normalized = normalize_url("https://example.com/job/123?utm_source=x&gh_jid=999")
    assert "utm_source" not in normalized
    assert "gh_jid=999" in normalized


def test_normalize_url_strips_trailing_slash_but_not_root() -> None:
    assert normalize_url("https://example.com/job/123/") == "https://example.com/job/123"
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_parse_posted_at_iso_is_exact() -> None:
    observed = datetime(2026, 8, 5, 12, 0, 0)
    posted_at, quality = parse_posted_at("2026-08-04", observed)
    assert quality is PostedAtQuality.EXACT
    assert posted_at is not None and posted_at.date().isoformat() == "2026-08-04"


def test_parse_posted_at_relative() -> None:
    observed = datetime(2026, 8, 5, 12, 0, 0)
    posted_at, quality = parse_posted_at("2 days ago", observed)
    assert quality is PostedAtQuality.RELATIVE
    assert posted_at is not None and (observed - posted_at).days == 2


def test_parse_posted_at_none_is_unknown() -> None:
    """Matches every LinkedIn probe run: posted_at_raw was null 40/40 times."""
    posted_at, quality = parse_posted_at(None, datetime(2026, 8, 5))
    assert posted_at is None
    assert quality is PostedAtQuality.UNKNOWN


def test_build_candidate_computes_description_chars_from_description() -> None:
    observation = SourceJobObservation(
        source=SourceName.INDEED,
        source_job_id="abc123",
        source_url="https://ca.indeed.com/viewjob?jk=abc123",
        apply_url_raw="https://example.com/apply/1",
        title_raw="  Software Engineer  ",
        company_raw="Acme Corp",
        location_raw="Toronto, ON, CA",
        posted_at_raw="2026-08-04",
        description_raw="x" * 500,
        observed_at=datetime(2026, 8, 5),
        run_id="run-1",
    )
    candidate = build_candidate(observation)
    assert candidate.description_chars == 500
    assert candidate.title == "Software Engineer"
    assert candidate.workplace_type is WorkplaceType.UNKNOWN
