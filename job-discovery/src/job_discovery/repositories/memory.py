"""In-memory JobRepository. Used for unit tests and for validating the
domain design end to end before a SQLite or DynamoDB implementation exists.

Field-update policy on a repeat observation: description/eligibility/score
fields are refreshed because they drive scoring and staleness decisions.
canonical_title/company/location are set once from the first observation and
never overwritten -- changing them on a later observation would rewrite the
identity that the dedup keys were computed against.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from job_discovery.domain.interfaces import JobRepository
from job_discovery.domain.models import (
    CoarseScore,
    DedupKey,
    DedupKeyKind,
    DedupMatch,
    EligibilityDecision,
    JobCategory,
    JobQuery,
    JobRecord,
    JobSourceListing,
    ListingStatus,
    NormalizedJobCandidate,
    SourceName,
    UpsertResult,
    UpsertStatus,
)


class InMemoryJobRepository(JobRepository):
    def __init__(self) -> None:
        self._records: dict[UUID, JobRecord] = {}
        self._listings: dict[UUID, JobSourceListing] = {}
        self._listing_by_source: dict[tuple[SourceName, str], UUID] = {}
        self._key_index: dict[tuple[DedupKeyKind, str], UUID] = {}
        self._listing_ids_by_job: dict[UUID, list[UUID]] = {}

    def upsert_observation(
        self,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
        category: JobCategory | None = None,
    ) -> UpsertResult:
        existing_listing_id = self._listing_by_source.get((candidate.source, candidate.source_job_id))
        if existing_listing_id is not None:
            return self._update_existing_listing(existing_listing_id, candidate, eligibility)

        merge_job_id, merge_matched_by = self._find_merge_match(keys)
        if merge_job_id is not None:
            return self._add_listing_to_job(merge_job_id, candidate, eligibility, keys, merge_matched_by)

        weak_candidate_job_id = self._find_weak_candidate(keys)
        return self._create_job(
            candidate, eligibility, keys, category, possible_duplicate_of=weak_candidate_job_id
        )

    def get_record(self, job_id: UUID) -> JobRecord | None:
        return self._records.get(job_id)

    def find_matches(self, keys: list[DedupKey]) -> list[DedupMatch]:
        matches: list[DedupMatch] = []
        for key in keys:
            job_id = self._key_index.get((key.kind, key.value))
            if job_id is not None:
                matches.append(DedupMatch(job_id=job_id, matched_by=key.kind, matched_key=key.value))
        return matches

    def get_listing(self, source: SourceName, source_job_id: str) -> JobSourceListing | None:
        listing_id = self._listing_by_source.get((source, source_job_id))
        return self._listings.get(listing_id) if listing_id is not None else None

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        return [self._listings[lid] for lid in self._listing_ids_by_job.get(job_id, [])]

    def query(self, query: JobQuery) -> list[JobRecord]:
        results = list(self._records.values())
        if query.eligibility_status is not None:
            results = [r for r in results if r.eligibility_status == query.eligibility_status]
        if query.min_score is not None:
            results = [r for r in results if r.coarse_score is not None and r.coarse_score >= query.min_score]
        if query.source is not None:
            job_ids_for_source = {
                listing.job_id for listing in self._listings.values() if listing.source == query.source
            }
            results = [r for r in results if r.job_id in job_ids_for_source]
        return results[: query.limit]

    def record_score(self, job_id: UUID, score: CoarseScore, score_version: str) -> None:
        record = self._records.get(job_id)
        if record is None:
            raise KeyError(f"no JobRecord for {job_id}")
        record.coarse_score = score.score
        record.coarse_score_reasoning = score.reasoning
        record.score_model = score.model
        record.score_version = score_version
        record.scored_at = score.scored_at
        record.updated_at = score.scored_at
        if score.required_years_min is not None:
            record.required_years_min = score.required_years_min
        if score.required_years_max is not None:
            record.required_years_max = score.required_years_max
        if score.requirement_keywords:
            record.requirement_keywords = score.requirement_keywords

    def record_requirements(self, job_id: UUID, score: CoarseScore) -> None:
        record = self._records.get(job_id)
        if record is None:
            raise KeyError(f"no JobRecord for {job_id}")
        if score.required_years_min is not None:
            record.required_years_min = score.required_years_min
        if score.required_years_max is not None:
            record.required_years_max = score.required_years_max
        if score.requirement_keywords:
            record.requirement_keywords = score.requirement_keywords

    # Only these two tiers auto-merge into an existing JobRecord. A real
    # Lambda run against TD showed two different requisitions colliding on
    # COMPANY_TITLE_LOCATION alone (identical title+company+location, but
    # apply_url_canonical differed) -- that tier is not strong enough to
    # merge on, only to flag. See _find_weak_candidate.
    _MERGE_KEY_KINDS = (DedupKeyKind.APPLY_URL, DedupKeyKind.DESCRIPTION_HASH)

    def _find_merge_match(self, keys: list[DedupKey]) -> tuple[UUID | None, DedupKeyKind | None]:
        for kind in self._MERGE_KEY_KINDS:
            key = next((k for k in keys if k.kind is kind), None)
            if key is None:
                continue
            job_id = self._key_index.get((key.kind, key.value))
            if job_id is not None:
                return job_id, key.kind
        return None, None

    def _find_weak_candidate(self, keys: list[DedupKey]) -> UUID | None:
        key = next((k for k in keys if k.kind is DedupKeyKind.COMPANY_TITLE_LOCATION), None)
        if key is None:
            return None
        return self._key_index.get((key.kind, key.value))

    def _update_existing_listing(
        self, listing_id: UUID, candidate: NormalizedJobCandidate, eligibility: EligibilityDecision
    ) -> UpsertResult:
        listing = self._listings[listing_id]
        job = self._records[listing.job_id]

        listing.last_seen_at = candidate.observed_at
        listing.last_seen_run_id = candidate.run_id
        listing.first_miss_at = None
        listing.consecutive_misses = 0
        listing.status = ListingStatus.ACTIVE
        if candidate.apply_url_canonical:
            listing.apply_url_canonical = candidate.apply_url_canonical
        if candidate.posted_at is not None:
            listing.posted_at = candidate.posted_at
            listing.posted_at_raw = candidate.posted_at_raw
            listing.posted_at_quality = candidate.posted_at_quality

        changed = self._refresh_record_fields(job, candidate, eligibility)
        if changed:
            job.updated_at = candidate.observed_at

        status = UpsertStatus.LISTING_UPDATED if changed else UpsertStatus.LISTING_UNCHANGED
        return UpsertResult(status=status, job_id=job.job_id, listing_id=listing.listing_id, matched_by=DedupKeyKind.SOURCE_ID)

    def _add_listing_to_job(
        self,
        job_id: UUID,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
        matched_by: DedupKeyKind | None,
    ) -> UpsertResult:
        job = self._records[job_id]
        self._refresh_record_fields(job, candidate, eligibility)
        job.updated_at = candidate.observed_at

        listing = self._new_listing(job_id, candidate)
        self._register_listing(listing)
        self._register_keys(keys, job_id)

        return UpsertResult(status=UpsertStatus.LISTING_ADDED, job_id=job_id, listing_id=listing.listing_id, matched_by=matched_by)

    def _create_job(
        self,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
        category: JobCategory | None = None,
        possible_duplicate_of: UUID | None = None,
    ) -> UpsertResult:
        job = JobRecord(
            job_id=uuid4(),
            canonical_title=candidate.title,
            canonical_company=candidate.company,
            canonical_location=candidate.location,
            workplace_type=candidate.workplace_type,
            description=candidate.description,
            description_chars=candidate.description_chars,
            description_hash=candidate.description_hash,
            salary_text=candidate.salary_text,
            job_category=category,
            possible_duplicate_of=possible_duplicate_of,
            duplicate_matched_by=DedupKeyKind.COMPANY_TITLE_LOCATION if possible_duplicate_of else None,
            eligibility_status=eligibility.status,
            filter_codes=eligibility.codes,
            filter_version=eligibility.filter_version,
            first_discovered_run_id=candidate.run_id,
            created_at=candidate.observed_at,
            updated_at=candidate.observed_at,
        )
        self._records[job.job_id] = job

        listing = self._new_listing(job.job_id, candidate)
        self._register_listing(listing)
        self._register_keys(keys, job.job_id)

        return UpsertResult(
            status=UpsertStatus.JOB_CREATED,
            job_id=job.job_id,
            listing_id=listing.listing_id,
            matched_by=None,
            possible_duplicate_of=possible_duplicate_of,
        )

    def _refresh_record_fields(
        self, job: JobRecord, candidate: NormalizedJobCandidate, eligibility: EligibilityDecision
    ) -> bool:
        changed = False
        if candidate.description is not None and candidate.description != job.description:
            job.description = candidate.description
            job.description_chars = candidate.description_chars
            job.description_hash = candidate.description_hash
            changed = True
        if eligibility.status != job.eligibility_status or eligibility.codes != job.filter_codes:
            job.eligibility_status = eligibility.status
            job.filter_codes = eligibility.codes
            job.filter_version = eligibility.filter_version
            changed = True
        return changed

    def _new_listing(self, job_id: UUID, candidate: NormalizedJobCandidate) -> JobSourceListing:
        return JobSourceListing(
            listing_id=uuid4(),
            job_id=job_id,
            source=candidate.source,
            source_job_id=candidate.source_job_id,
            source_url=candidate.source_url,
            apply_url_canonical=candidate.apply_url_canonical,
            posted_at=candidate.posted_at,
            posted_at_raw=candidate.posted_at_raw,
            posted_at_quality=candidate.posted_at_quality,
            first_seen_at=candidate.observed_at,
            last_seen_at=candidate.observed_at,
            last_seen_run_id=candidate.run_id,
        )

    def _register_listing(self, listing: JobSourceListing) -> None:
        self._listings[listing.listing_id] = listing
        self._listing_by_source[(listing.source, listing.source_job_id)] = listing.listing_id
        self._listing_ids_by_job.setdefault(listing.job_id, []).append(listing.listing_id)

    def _register_keys(self, keys: list[DedupKey], job_id: UUID) -> None:
        for key in keys:
            self._key_index.setdefault((key.kind, key.value), job_id)
