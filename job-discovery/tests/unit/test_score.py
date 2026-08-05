from datetime import datetime

from job_discovery.application.ingest import ingest_observation
from job_discovery.application.score import score_eligible_jobs
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import CoarseScore, JobRecord, ScoringProfile, SourceJobObservation, SourceName
from job_discovery.repositories.memory import InMemoryJobRepository

CONFIG = FilterConfig(filter_version="v1", min_description_chars=0)
PROFILE = ScoringProfile(skills=["Python"])


class FakeScorer:
    """Implements CoarseScorer without any network dependency."""

    def __init__(self, fixed_score: int = 7, fail_titles: set[str] | None = None) -> None:
        self.fixed_score = fixed_score
        self.fail_titles = fail_titles or set()
        self.calls: list[str] = []

    def score(self, job: JobRecord, profile: ScoringProfile) -> CoarseScore:
        self.calls.append(job.canonical_title)
        if job.canonical_title in self.fail_titles:
            raise RuntimeError("simulated scorer failure")
        return CoarseScore(score=self.fixed_score, reasoning="fake", model="fake-model", scored_at=datetime(2026, 8, 5))


def _observation(source_job_id: str, title: str) -> SourceJobObservation:
    # description text must be distinct per posting -- identical text across
    # two different fake jobs collides on the DESCRIPTION_HASH dedup tier and
    # silently merges them into one JobRecord, which is exactly the bug this
    # helper used to have.
    return SourceJobObservation(
        source=SourceName.WORKDAY,
        source_job_id=source_job_id,
        source_url=f"https://example.com/{source_job_id}",
        title_raw=title,
        company_raw="Acme",
        location_raw="Toronto, ON",
        description_raw=f"{title} " * 100,
        observed_at=datetime(2026, 8, 5),
        run_id="run-1",
    )


def test_scores_only_eligible_jobs() -> None:
    repo = InMemoryJobRepository()
    ingest_observation(_observation("1", "Software Engineer"), repo, CONFIG)
    ingest_observation(_observation("2", "Staff Software Engineer"), repo, CONFIG)  # excluded_title

    scorer = FakeScorer()
    scored = score_eligible_jobs(repo, scorer, PROFILE, score_version="v1")

    assert len(scored) == 1
    assert scored[0].canonical_title == "Software Engineer"
    assert scored[0].coarse_score == 7
    assert scored[0].score_version == "v1"


def test_does_not_rescore_same_version() -> None:
    repo = InMemoryJobRepository()
    ingest_observation(_observation("1", "Software Engineer"), repo, CONFIG)
    scorer = FakeScorer()

    score_eligible_jobs(repo, scorer, PROFILE, score_version="v1")
    score_eligible_jobs(repo, scorer, PROFILE, score_version="v1")

    assert scorer.calls == ["Software Engineer"]


def test_rescopes_when_score_version_changes() -> None:
    repo = InMemoryJobRepository()
    ingest_observation(_observation("1", "Software Engineer"), repo, CONFIG)
    scorer = FakeScorer()

    score_eligible_jobs(repo, scorer, PROFILE, score_version="v1")
    score_eligible_jobs(repo, scorer, PROFILE, score_version="v2")

    assert scorer.calls == ["Software Engineer", "Software Engineer"]


def test_one_failure_does_not_block_the_rest_of_the_batch() -> None:
    repo = InMemoryJobRepository()
    ingest_observation(_observation("1", "Software Engineer"), repo, CONFIG)
    ingest_observation(_observation("2", "Backend Developer"), repo, CONFIG)

    scorer = FakeScorer(fail_titles={"Software Engineer"})
    scored = score_eligible_jobs(repo, scorer, PROFILE, score_version="v1")

    assert len(scored) == 1
    assert scored[0].canonical_title == "Backend Developer"
