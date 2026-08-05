"""Compute dedup keys for a candidate, strongest first.

Matches architecture doc 5.1: source+source_job_id, then canonical apply URL,
then description hash, then company+title+location as a weak fallback.
Callers (JobRepository implementations) must probe in this order and stop at
the first match -- see domain/interfaces.py.
"""

from __future__ import annotations

from job_discovery.domain.models import DedupKey, DedupKeyKind, NormalizedJobCandidate


def compute_dedup_keys(candidate: NormalizedJobCandidate) -> list[DedupKey]:
    keys = [
        DedupKey(
            kind=DedupKeyKind.SOURCE_ID,
            value=f"{candidate.source.value}:{candidate.source_job_id}",
        )
    ]

    if candidate.apply_url_canonical:
        keys.append(DedupKey(kind=DedupKeyKind.APPLY_URL, value=candidate.apply_url_canonical))

    if candidate.description_hash:
        keys.append(DedupKey(kind=DedupKeyKind.DESCRIPTION_HASH, value=candidate.description_hash))

    if candidate.normalized_location:
        weak_value = f"{candidate.normalized_company}|{candidate.normalized_title}|{candidate.normalized_location}"
        keys.append(DedupKey(kind=DedupKeyKind.COMPANY_TITLE_LOCATION, value=weak_value))

    return keys
