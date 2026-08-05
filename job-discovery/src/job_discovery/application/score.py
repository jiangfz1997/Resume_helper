"""Score eligible, unscored records. Mirrors ingest.py: thin glue between the
domain interfaces, not business logic of its own.

Selection matches architecture doc 6.2: eligibility_status=eligible AND
(coarse_score IS NULL OR score_version changed). Catches per-record so one
flaky external-API call does not drop the rest of the batch -- external LLM
calls fail far more often than local domain logic, unlike ingest_observation,
which lets exceptions propagate.
"""

from __future__ import annotations

import logging

from job_discovery.domain.interfaces import CoarseScorer, JobRepository
from job_discovery.domain.models import EligibilityStatus, JobQuery, JobRecord, ScoringProfile

log = logging.getLogger(__name__)


def score_eligible_jobs(
    repository: JobRepository,
    scorer: CoarseScorer,
    profile: ScoringProfile,
    score_version: str,
    limit: int = 1000,
) -> list[JobRecord]:
    candidates = [
        record
        for record in repository.query(JobQuery(eligibility_status=EligibilityStatus.ELIGIBLE, limit=limit))
        if record.coarse_score is None or record.score_version != score_version
    ]

    scored: list[JobRecord] = []
    for record in candidates:
        try:
            result = scorer.score(record, profile)
        except Exception as exc:
            log.warning("scoring failed for %s (%s): %s", record.job_id, record.canonical_title, exc)
            continue
        repository.record_score(record.job_id, result, score_version)
        updated = repository.get_record(record.job_id)
        if updated is not None:
            scored.append(updated)
    return scored
