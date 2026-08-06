"""Abstractions for the two things Phase 1 must not depend on directly:
a specific scraping mechanism, and a specific database."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from job_discovery.domain.models import (
    CoarseScore,
    DedupKey,
    DedupMatch,
    EligibilityDecision,
    JobQuery,
    JobRecord,
    JobSourceListing,
    NormalizedJobCandidate,
    ScoringProfile,
    SearchQuery,
    SourceJobObservation,
    SourceJobRef,
    SourceName,
    UpsertResult,
)


class JobSource(Protocol):
    """One implementation per source family (Workday CXS, jobspy-backed
    aggregators, ...). search() and fetch_detail() are separate because some
    sources need two requests per posting (Workday) and others already have
    the full description after search (jobspy) -- fetch_detail() on those
    just wraps the cached result, it does not re-fetch."""

    source: SourceName

    def search(self, query: SearchQuery) -> list[SourceJobRef]: ...

    def fetch_detail(self, ref: SourceJobRef) -> SourceJobObservation: ...


class JobRepository(Protocol):
    """Backed by an in-memory dict for Phase 1, SQLite for local runs later,
    DynamoDB in the cloud -- callers must not depend on which."""

    def upsert_observation(
        self,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
    ) -> UpsertResult: ...

    def get_record(self, job_id: UUID) -> JobRecord | None: ...

    def find_matches(self, keys: list[DedupKey]) -> list[DedupMatch]: ...

    def get_listing(self, source: SourceName, source_job_id: str) -> JobSourceListing | None: ...

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]: ...

    def query(self, query: JobQuery) -> list[JobRecord]: ...

    def record_score(self, job_id: UUID, score: CoarseScore, score_version: str) -> None: ...

    def record_requirements(self, job_id: UUID, score: CoarseScore) -> None: ...


class CoarseScorer(Protocol):
    """One call scores one job. Callers decide which records qualify
    (architecture doc 6.2: eligible AND not yet scored) -- this interface
    does not know about the repository."""

    def score(self, job: JobRecord, profile: ScoringProfile) -> CoarseScore: ...
