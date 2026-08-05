"""Manual, real-API check of GeminiCoarseScorer against one realistic job.
Not part of pytest -- see tests/unit/test_gemini_scorer.py for the offline
equivalent (monkeypatched, no network, no quota spent).

Requires GEMINI_API_KEY and GEMINI_MODEL in the environment. GEMINI_MODEL is
intentionally not defaulted in code -- model names on this API move fast:
`gemini-2.5-flash`, listed by the models endpoint as available, already
returned 404 ("no longer available to new users") on 2026-08-05. Don't trust
a name still appearing in the list; verify with an actual generateContent
call. `gemini-3.6-flash` worked as of that date -- treat this as a data
point, not a default, since it will go stale too.

    GEMINI_API_KEY=... GEMINI_MODEL=... PYTHONPATH=src python scripts/live_probe_gemini.py
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from job_discovery.domain.models import EligibilityStatus, JobRecord, ScoringProfile, WorkplaceType
from job_discovery.scoring.gemini_scorer import GeminiCoarseScorer

# Real posting from the live_probe_workday.py run on 2026-08-05.
JOB = JobRecord(
    job_id=uuid4(),
    canonical_title="Software Engineer III",
    canonical_company="TD Bank",
    canonical_location="Toronto, Ontario",
    workplace_type=WorkplaceType.ONSITE,
    description=(
        "Work Location: Toronto, Ontario, Canada. Hours: 37.5. As a member of the "
        "Software Engineering team, you will design, develop and maintain high quality "
        "software solutions. Experience with Java, Spring Boot, REST APIs, SQL, and "
        "cloud platforms (AWS or Azure) is required. CI/CD pipeline experience preferred."
    ),
    description_chars=350,
    eligibility_status=EligibilityStatus.ELIGIBLE,
    created_at=datetime(2026, 8, 5),
    updated_at=datetime(2026, 8, 5),
)

PROFILE = ScoringProfile(
    skills=["Python", "Java", "AWS", "REST APIs", "SQL", "CI/CD"],
    target_titles=["Software Engineer", "Backend Developer"],
    min_years_experience=2,
    location_preference="Toronto",
)


def main() -> None:
    scorer = GeminiCoarseScorer()
    print(f"model: {scorer.model}")
    result = scorer.score(JOB, PROFILE)
    print(f"score: {result.score}/10")
    print(f"reasoning: {result.reasoning}")
    print(f"scored_at: {result.scored_at}")


if __name__ == "__main__":
    main()
