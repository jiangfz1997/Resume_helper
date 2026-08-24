from datetime import datetime, timezone
from uuid import uuid4

from job_discovery.domain.models import EligibilityStatus, JobRecord, WorkplaceType
from job_discovery.domain.scoring_policy import effective_required_years, is_scoreable_by_years, scoring_priority


def _job(minimum: int | None, maximum: int | None = None, *, new_grad: bool = False) -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        job_id=uuid4(), canonical_title="Software Engineer", canonical_company="Example",
        workplace_type=WorkplaceType.UNKNOWN, description_chars=500,
        required_years_min=minimum, required_years_max=maximum, is_new_grad=new_grad,
        eligibility_status=EligibilityStatus.ELIGIBLE, created_at=now, updated_at=now,
    )


def test_range_uses_its_upper_bound_for_scoring_cap() -> None:
    job = _job(5, 8)
    assert effective_required_years(job) == 8
    assert is_scoreable_by_years(job, 5) is False


def test_three_to_five_range_stays_scoreable_at_cap_five() -> None:
    assert is_scoreable_by_years(_job(3, 5), 5) is True


def test_unstated_requirement_stays_scoreable() -> None:
    assert is_scoreable_by_years(_job(None), 5) is True


def test_priority_reserves_budget_for_early_career_roles() -> None:
    assert scoring_priority(_job(None, new_grad=True)) == 0
    assert scoring_priority(_job(3)) == 1
    assert scoring_priority(_job(None)) == 1
    assert scoring_priority(_job(5)) == 2
