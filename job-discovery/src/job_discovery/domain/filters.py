"""Deterministic pre-LLM filtering. Never mutate a candidate to attach a
verdict -- return an EligibilityDecision instead (architecture doc 6.1:
filtering does not delete records, it labels them, so a rule change can be
re-applied without re-scraping).

Required-years extraction is out of scope here: it needs text mining over
the description that has not been built yet, so required_years_min/max stay
unset on NormalizedJobCandidate and this module does not filter on them.
Add that filter when the extractor exists rather than faking thresholds now.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from job_discovery.domain.models import (
    EligibilityDecision,
    EligibilityStatus,
    FilterCode,
    JobCategory,
    NormalizedJobCandidate,
    WorkplaceType,
)


# Split by track so classify_category() below can tag a job as SDE or QA.
# "engineer" alone is deliberately excluded from both: it would also match
# Sales Engineer, Field Engineer, Mechanical Engineer, none of which belong
# here. To add a third track later, add another *_TITLE_KEYWORDS list, a
# JobCategory value, and one more branch in classify_category().
SDE_TITLE_KEYWORDS: list[str] = [
    "software engineer",
    "software developer",
    "backend",
    "back-end",
    "back end",
    "frontend",
    "front-end",
    "front end",
    "full stack",
    "full-stack",
    "fullstack",
    "developer",
    "sde",
    "swe",
]

QA_TITLE_KEYWORDS: list[str] = [
    "qa engineer",
    "quality assurance",
    "qa analyst",
    "sdet",
    "test engineer",
    "test automation",
    "automation engineer",
]

# Empty list means "no restriction" (same convention as accepted_locations),
# so a caller that never sets this keeps the old, more permissive behavior.
# The default below is a starting point for a software engineer / QA search,
# not a universal list -- tune it per search, e.g. via the Lambda event.
DEFAULT_INCLUDE_TITLE_KEYWORDS: list[str] = [*SDE_TITLE_KEYWORDS, *QA_TITLE_KEYWORDS]


def classify_category(normalized_title: str) -> JobCategory | None:
    """Tag a job as SDE or QA from its title. Independent from
    apply_hard_filters below on purpose: eligibility decides whether a
    posting is kept at all, this only decides which track it belongs to, and
    the two must stay free to change separately. Checked in QA-first order
    because "automation engineer" and similar QA titles could otherwise also
    read as a plain "developer"/"engineer" SDE match."""

    if any(keyword in normalized_title for keyword in QA_TITLE_KEYWORDS):
        return JobCategory.QA
    if any(keyword in normalized_title for keyword in SDE_TITLE_KEYWORDS):
        return JobCategory.SDE
    return None


class FilterConfig(BaseModel):
    filter_version: str
    accepted_locations: list[str] = Field(default_factory=list)
    include_title_keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE_TITLE_KEYWORDS))
    exclude_title_keywords: list[str] = Field(
        default_factory=lambda: ["staff", "principal", "director", "vp", "vice president", "head of"]
    )
    review_title_keywords: list[str] = Field(default_factory=lambda: ["senior", "sr.", "lead"])
    min_description_chars: int = 300


def apply_hard_filters(candidate: NormalizedJobCandidate, config: FilterConfig) -> EligibilityDecision:
    exclude_codes: list[FilterCode] = []
    review_codes: list[FilterCode] = []

    if not _location_ok(candidate, config):
        exclude_codes.append(FilterCode.LOCATION_MISMATCH)

    title = candidate.normalized_title
    if any(keyword in title for keyword in config.exclude_title_keywords):
        exclude_codes.append(FilterCode.EXCLUDED_TITLE)
    elif any(keyword in title for keyword in config.review_title_keywords):
        review_codes.append(FilterCode.REVIEW_TITLE)

    # A CNC Machinist posting only got excluded by luck (wrong location) in a
    # real run on 2026-08-05 -- location and seniority checks alone let any
    # job category through. This is the actual relevance gate.
    if config.include_title_keywords and not any(keyword in title for keyword in config.include_title_keywords):
        exclude_codes.append(FilterCode.TITLE_NOT_RELEVANT)

    if candidate.description is None:
        review_codes.append(FilterCode.DESCRIPTION_MISSING)
    elif candidate.description_chars < config.min_description_chars:
        review_codes.append(FilterCode.DESCRIPTION_TOO_SHORT)

    if exclude_codes:
        return EligibilityDecision(
            status=EligibilityStatus.EXCLUDED, codes=exclude_codes, filter_version=config.filter_version
        )
    if review_codes:
        return EligibilityDecision(
            status=EligibilityStatus.REVIEW, codes=review_codes, filter_version=config.filter_version
        )
    return EligibilityDecision(status=EligibilityStatus.ELIGIBLE, codes=[], filter_version=config.filter_version)


def _location_ok(candidate: NormalizedJobCandidate, config: FilterConfig) -> bool:
    if candidate.workplace_type is WorkplaceType.REMOTE:
        return True
    if not config.accepted_locations:
        return True
    if candidate.normalized_location is None:
        return True
    return any(accepted.casefold() in candidate.normalized_location for accepted in config.accepted_locations)
