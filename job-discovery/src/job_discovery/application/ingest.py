"""Single entry point wiring normalize -> dedup keys -> filter -> persist.

Kept as one function deliberately: a Lambda handler should stay thin and call
this, not re-implement the pipeline order inline.
"""

from __future__ import annotations

from job_discovery.domain.deduplicate import compute_dedup_keys
from job_discovery.domain.filters import FilterConfig, apply_hard_filters, classify_category
from job_discovery.domain.interfaces import JobRepository
from job_discovery.domain.models import SourceJobObservation, UpsertResult
from job_discovery.domain.normalize import build_candidate


def ingest_observation(
    observation: SourceJobObservation,
    repository: JobRepository,
    filter_config: FilterConfig,
) -> UpsertResult:
    candidate = build_candidate(observation)
    eligibility = apply_hard_filters(candidate, filter_config)
    category = classify_category(candidate.normalized_title)
    keys = compute_dedup_keys(candidate)
    return repository.upsert_observation(candidate, eligibility, keys, category)
