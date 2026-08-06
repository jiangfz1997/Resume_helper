from __future__ import annotations

import logging
from datetime import timezone
from uuid import UUID

from job_discovery.dashboard.interfaces import DashboardUserStateRepository
from job_discovery.dashboard.models import DashboardJobUserStatus
from job_discovery.domain.interfaces import CoarseScorer, JobRepository
from job_discovery.domain.models import EligibilityStatus, JobQuery, JobRecord

log = logging.getLogger(__name__)


def score_jobs_for_users(
    repository: JobRepository,
    user_data: DashboardUserStateRepository,
    scorer: CoarseScorer,
    prompt_version: str,
    limit: int = 100,
    user_ids: set[str] | None = None,
    job_ids: set[UUID] | None = None,
) -> tuple[int, int]:
    jobs = repository.query(JobQuery(eligibility_status=EligibilityStatus.ELIGIBLE, limit=1000))
    if job_ids is not None:
        jobs = [job for job in jobs if job.job_id in job_ids]
    jobs.sort(key=_created_timestamp, reverse=True)
    profiles = [
        profile for profile in user_data.list_scoring_profiles()
        if profile.active and (user_ids is None or profile.user_id in user_ids)
    ]
    snapshots = {profile.user_id: user_data.get_snapshot(profile.user_id) for profile in profiles}
    existing = {
        (profile.user_id, state.job_id, state.profile_version, state.score_version)
        for profile in profiles
        for state in snapshots[profile.user_id].jobs
        if state.coarse_score is not None
    }
    scored = 0
    errors = 0
    for profile in profiles:
        attempted = 0
        for job in jobs:
            score_version = f"{prompt_version}:{job.description_hash or 'no-description'}"
            current_state = next((state for state in snapshots[profile.user_id].jobs if state.job_id == job.job_id), None)
            if current_state and current_state.status in {
                DashboardJobUserStatus.APPLIED,
                DashboardJobUserStatus.REJECTED,
            }:
                continue
            if (profile.user_id, job.job_id, profile.profile_version, score_version) in existing:
                continue
            if attempted >= limit:
                break
            attempted += 1
            try:
                result = scorer.score(job, profile.to_scoring_profile())
                user_data.record_user_score(
                    profile.user_id, job.job_id, result, score_version, profile.profile_version
                )
                repository.record_requirements(job.job_id, result)
                scored += 1
            except Exception as exc:
                errors += 1
                user_data.record_user_score_failure(
                    profile.user_id, job.job_id, score_version, profile.profile_version, str(exc)
                )
                log.warning("personalized scoring failed for user %s job %s: %s", profile.user_id, job.job_id, exc)
    return scored, errors


def _created_timestamp(job: JobRecord) -> float:
    created_at = job.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.timestamp()
