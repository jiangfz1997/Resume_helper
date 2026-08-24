from __future__ import annotations

from job_discovery.domain.models import JobRecord


def effective_required_years(job: JobRecord) -> int | None:
    """Conservative bound used for scoring eligibility.

    A range such as 5-8 years is treated as eight, while a single value or
    open-ended minimum uses the parsed minimum. This is intentionally stricter
    than "can a candidate at the bottom of the range apply?": the scoring
    budget is reserved for early-career roles.
    """
    return job.required_years_max if job.required_years_max is not None else job.required_years_min


def is_scoreable_by_years(job: JobRecord, max_required_years: int | None) -> bool:
    if max_required_years is None:
        return True
    years = effective_required_years(job)
    return years is None or years <= max_required_years


def scoring_priority(job: JobRecord) -> int:
    """Lower values are scored first.

    New-grad roles with no more than three stated years lead, followed by all
    other 0-3 year or unstated roles. Four- and five-year roles use whatever
    budget remains after the early-career queue.
    """
    years = effective_required_years(job)
    if job.is_new_grad and (years is None or years <= 3):
        return 0
    if years is None or years <= 3:
        return 1
    return 2
