"""Turn one SourceJobObservation into a NormalizedJobCandidate.

URL and posted_at handling exist because probe data showed both are messy in
practice: TD and CIBC postings were reachable through both Indeed and Workday
with matching job_url_direct values (this is the apply_url_canonical dedup
signal), and LinkedIn never returned a posted date across any probe run while
Indeed's hours_old filter let a seven-week-old posting through anyway.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_discovery.domain.models import (
    NormalizedJobCandidate,
    PostedAtQuality,
    SourceJobObservation,
    WorkplaceType,
)
from job_discovery.domain.seniority import assess_seniority
from job_discovery.domain.years import extract_years

# Known cross-site tracking params. Deliberately not a blanket "strip every
# query string" rule -- ATS URLs carry meaningful identifiers (Greenhouse job
# ids, Workday requisition numbers) in the query string on some hosts, and
# stripping those would break the apply_url_canonical dedup key rather than
# help it. Extend this set when a concrete false-negative shows up; do not
# guess ahead of evidence.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"ref", "refid", "trk", "trackingid", "source", "gh_src", "gh_jid_ref"}

_WORKPLACE_KEYWORDS: tuple[tuple[str, WorkplaceType], ...] = (
    ("remote", WorkplaceType.REMOTE),
    ("work from home", WorkplaceType.REMOTE),
    ("wfh", WorkplaceType.REMOTE),
    ("hybrid", WorkplaceType.HYBRID),
    ("on-site", WorkplaceType.ONSITE),
    ("onsite", WorkplaceType.ONSITE),
)

# Explicit source-provided hint (Workday's remoteType, jobspy's is_remote)
# always wins over sniffing the location string -- the guess is a fallback
# for sources that don't tell us directly.
_WORKPLACE_TYPE_HINTS: dict[str, WorkplaceType] = {
    "on site": WorkplaceType.ONSITE,
    "onsite": WorkplaceType.ONSITE,
    "on-site": WorkplaceType.ONSITE,
    "hybrid": WorkplaceType.HYBRID,
    "remote": WorkplaceType.REMOTE,
}

_RELATIVE_POSTED_RE = re.compile(
    r"^\s*(?:posted\s+)?(\d+)\s*\+?\s*(hour|day|week|month)s?\s+ago\s*$", re.IGNORECASE
)
# Workday returns "Posted Today" / "Posted Just Posted"-style text; other
# sources may omit the "posted" prefix entirely.
_JUST_POSTED_RE = re.compile(r"^\s*(?:posted\s+)?(just\s+posted|today)\s*$", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_RELATIVE_UNIT_TO_TIMEDELTA = {
    "hour": lambda n: timedelta(hours=n),
    "day": lambda n: timedelta(days=n),
    "week": lambda n: timedelta(weeks=n),
    "month": lambda n: timedelta(days=n * 30),
}


def normalize_url(raw: str) -> str:
    """Lowercase scheme/host, drop fragment and known tracking params, drop
    a bare trailing slash. Idempotent: normalize_url(normalize_url(x)) == normalize_url(x).
    """
    parsed = urlparse(raw.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept_params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith(_TRACKING_PARAM_PREFIXES)
    ]
    kept_params.sort()
    query = urlencode(kept_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_company(raw: str) -> str:
    return " ".join(raw.strip().split()).casefold()


def normalize_title(raw: str) -> str:
    return " ".join(raw.strip().split()).casefold()


def normalize_location(raw: str | None) -> tuple[str | None, WorkplaceType]:
    """Fallback workplace-type guess from the location text. Prefer
    map_workplace_type_hint() over this whenever the source gives one
    directly (Workday's remoteType, jobspy's is_remote)."""
    if raw is None:
        return None, WorkplaceType.UNKNOWN
    cleaned = " ".join(raw.strip().split())
    lowered = cleaned.casefold()
    workplace_type = WorkplaceType.UNKNOWN
    for keyword, kind in _WORKPLACE_KEYWORDS:
        if keyword in lowered:
            workplace_type = kind
            break
    return (cleaned or None), workplace_type


def map_workplace_type_hint(raw: str | None) -> WorkplaceType | None:
    if raw is None:
        return None
    return _WORKPLACE_TYPE_HINTS.get(raw.strip().casefold())


def parse_posted_at(raw: str | None, observed_at: datetime) -> tuple[datetime | None, PostedAtQuality]:
    """LinkedIn returned null for posted_at in every probe run regardless of
    hours_old; that is UNKNOWN, not a parse failure, and callers must fall
    back to first_seen_at rather than treat it as "just posted"."""
    if raw is None or not raw.strip():
        return None, PostedAtQuality.UNKNOWN

    text = raw.strip()

    if _ISO_DATE_RE.match(text):
        try:
            return datetime.fromisoformat(text[:19]), PostedAtQuality.EXACT
        except ValueError:
            pass

    if _JUST_POSTED_RE.match(text):
        return observed_at, PostedAtQuality.RELATIVE

    relative = _RELATIVE_POSTED_RE.match(text)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2).lower()
        delta = _RELATIVE_UNIT_TO_TIMEDELTA[unit](amount)
        return observed_at - delta, PostedAtQuality.RELATIVE

    return None, PostedAtQuality.INFERRED


def build_candidate(observation: SourceJobObservation) -> NormalizedJobCandidate:
    normalized_location, guessed_workplace_type = normalize_location(observation.location_raw)
    workplace_type = map_workplace_type_hint(observation.workplace_type_raw) or guessed_workplace_type
    posted_at, posted_at_quality = parse_posted_at(observation.posted_at_raw, observation.observed_at)

    apply_url_canonical = (
        normalize_url(observation.apply_url_raw) if observation.apply_url_raw else None
    )

    description = observation.description_raw
    description_chars = len(description) if description else 0
    description_hash = (
        hashlib.sha256(description.encode("utf-8")).hexdigest() if description else None
    )

    title = observation.title_raw.strip()
    years = extract_years(description)
    seniority = assess_seniority(title, description)

    return NormalizedJobCandidate(
        source=observation.source,
        source_job_id=observation.source_job_id,
        source_url=observation.source_url,
        apply_url_raw=observation.apply_url_raw,
        apply_url_canonical=apply_url_canonical,
        title=title,
        normalized_title=normalize_title(observation.title_raw),
        company=observation.company_raw.strip(),
        normalized_company=normalize_company(observation.company_raw),
        location=normalized_location,
        normalized_location=normalized_location.casefold() if normalized_location else None,
        workplace_type=workplace_type,
        posted_at=posted_at,
        posted_at_raw=observation.posted_at_raw,
        posted_at_quality=posted_at_quality,
        description=description,
        description_chars=description_chars,
        description_hash=description_hash,
        salary_text=observation.salary_text_raw,
        required_years_min=years.minimum,
        required_years_max=years.maximum,
        years_mentioned=years.mentioned,
        is_new_grad=seniority.is_new_grad,
        new_grad_signals=seniority.signals,
        observed_at=observation.observed_at,
        run_id=observation.run_id,
    )
