"""DynamoDB-backed JobRepository.

Method names and control flow deliberately mirror repositories/memory.py
line for line -- same three-tier upsert_observation cascade (existing
listing by source -> APPLY_URL/DESCRIPTION_HASH auto-merge ->
COMPANY_TITLE_LOCATION flags without merging), so the two implementations
are easy to diff against each other and are held to identical behavior by
the shared contract tests in tests/unit/test_repository_contract.py.

Every read here is a primary-key read with ConsistentRead=True, and there
are no GSIs. An earlier version used two GSIs (source lookup,
eligibility_status) and hit a real AssertionError in a Lambda run on
2026-08-05: GSI reads are *always* eventually consistent in DynamoDB, code
had just written a new listing and immediately queried it back through the
GSI before replication caught up. See dynamodb_schema.py's module docstring
for the full story, including why moto could not have caught this.

dedup key writes use ConditionExpression=attribute_not_exists so two
concurrent invocations racing to claim the same key can't overwrite each
other -- first writer wins, the distributed equivalent of memory.py's
dict.setdefault.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import boto3
from boto3.dynamodb.conditions import Key

from job_discovery.domain.interfaces import JobRepository
from job_discovery.domain.models import (
    CoarseScore,
    DedupKey,
    DedupKeyKind,
    DedupMatch,
    EligibilityDecision,
    EligibilityStatus,
    FilterCode,
    JobQuery,
    JobRecord,
    JobSourceListing,
    ListingStatus,
    NormalizedJobCandidate,
    PostedAtQuality,
    SourceName,
    UpsertResult,
    UpsertStatus,
    WorkplaceType,
)


def _strip_none(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if v is not None}


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _paginated(operation: Any, **kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    resp = operation(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = operation(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def _record_to_item(record: JobRecord) -> dict[str, Any]:
    return _strip_none(
        {
            "job_id": str(record.job_id),
            "canonical_title": record.canonical_title,
            "canonical_company": record.canonical_company,
            "canonical_location": record.canonical_location,
            "workplace_type": record.workplace_type.value,
            "description": record.description,
            "description_chars": record.description_chars,
            "description_hash": record.description_hash,
            "salary_text": record.salary_text,
            "required_years_min": record.required_years_min,
            "required_years_max": record.required_years_max,
            "requirement_keywords": record.requirement_keywords,
            "possible_duplicate_of": str(record.possible_duplicate_of) if record.possible_duplicate_of else None,
            "duplicate_matched_by": record.duplicate_matched_by.value if record.duplicate_matched_by else None,
            "eligibility_status": record.eligibility_status.value,
            "filter_codes": [c.value for c in record.filter_codes],
            "filter_version": record.filter_version,
            "coarse_score": record.coarse_score,
            "coarse_score_reasoning": record.coarse_score_reasoning,
            "score_model": record.score_model,
            "score_version": record.score_version,
            "scored_at": record.scored_at.isoformat() if record.scored_at else None,
            "user_status": record.user_status,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
    )


def _item_to_record(item: dict[str, Any]) -> JobRecord:
    return JobRecord(
        job_id=UUID(item["job_id"]),
        canonical_title=item["canonical_title"],
        canonical_company=item["canonical_company"],
        canonical_location=item.get("canonical_location"),
        workplace_type=WorkplaceType(item["workplace_type"]),
        description=item.get("description"),
        description_chars=int(item["description_chars"]),
        description_hash=item.get("description_hash"),
        salary_text=item.get("salary_text"),
        required_years_min=_int_or_none(item.get("required_years_min")),
        required_years_max=_int_or_none(item.get("required_years_max")),
        requirement_keywords=list(item.get("requirement_keywords", [])),
        possible_duplicate_of=UUID(item["possible_duplicate_of"]) if item.get("possible_duplicate_of") else None,
        duplicate_matched_by=DedupKeyKind(item["duplicate_matched_by"]) if item.get("duplicate_matched_by") else None,
        eligibility_status=EligibilityStatus(item["eligibility_status"]),
        filter_codes=[FilterCode(c) for c in item.get("filter_codes", [])],
        filter_version=item.get("filter_version"),
        coarse_score=_int_or_none(item.get("coarse_score")),
        coarse_score_reasoning=item.get("coarse_score_reasoning"),
        score_model=item.get("score_model"),
        score_version=item.get("score_version"),
        scored_at=datetime.fromisoformat(item["scored_at"]) if item.get("scored_at") else None,
        user_status=item.get("user_status", "new"),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
    )


def _listing_to_item(listing: JobSourceListing) -> dict[str, Any]:
    return _strip_none(
        {
            "job_id": str(listing.job_id),
            "source_job_id_key": f"{listing.source.value}#{listing.source_job_id}",
            "listing_id": str(listing.listing_id),
            "source": listing.source.value,
            "source_job_id": listing.source_job_id,
            "source_url": listing.source_url,
            "apply_url_canonical": listing.apply_url_canonical,
            "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
            "posted_at_raw": listing.posted_at_raw,
            "posted_at_quality": listing.posted_at_quality.value,
            "first_seen_at": listing.first_seen_at.isoformat(),
            "last_seen_at": listing.last_seen_at.isoformat(),
            "first_miss_at": listing.first_miss_at.isoformat() if listing.first_miss_at else None,
            "consecutive_misses": listing.consecutive_misses,
            "last_seen_run_id": listing.last_seen_run_id,
            "status": listing.status.value,
        }
    )


def _item_to_listing(item: dict[str, Any]) -> JobSourceListing:
    return JobSourceListing(
        listing_id=UUID(item["listing_id"]),
        job_id=UUID(item["job_id"]),
        source=SourceName(item["source"]),
        source_job_id=item["source_job_id"],
        source_url=item["source_url"],
        apply_url_canonical=item.get("apply_url_canonical"),
        posted_at=datetime.fromisoformat(item["posted_at"]) if item.get("posted_at") else None,
        posted_at_raw=item.get("posted_at_raw"),
        posted_at_quality=PostedAtQuality(item["posted_at_quality"]),
        first_seen_at=datetime.fromisoformat(item["first_seen_at"]),
        last_seen_at=datetime.fromisoformat(item["last_seen_at"]),
        first_miss_at=datetime.fromisoformat(item["first_miss_at"]) if item.get("first_miss_at") else None,
        consecutive_misses=int(item.get("consecutive_misses", 0)),
        last_seen_run_id=item["last_seen_run_id"],
        status=ListingStatus(item.get("status", "active")),
    )


class DynamoDBJobRepository(JobRepository):
    # Only these two tiers auto-merge -- see repositories/memory.py for the
    # real Lambda run (TD, 2026-08-05) that showed why COMPANY_TITLE_LOCATION
    # alone must not merge.
    _MERGE_KEY_KINDS = (DedupKeyKind.APPLY_URL, DedupKeyKind.DESCRIPTION_HASH)

    def __init__(
        self,
        records_table: str,
        listings_table: str,
        dedup_keys_table: str,
        source_lookup_table: str,
        resource: Any = None,
    ) -> None:
        self._resource = resource or boto3.resource("dynamodb")
        self._records = self._resource.Table(records_table)
        self._listings = self._resource.Table(listings_table)
        self._dedup_keys = self._resource.Table(dedup_keys_table)
        self._source_lookup = self._resource.Table(source_lookup_table)

    def upsert_observation(
        self,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
    ) -> UpsertResult:
        existing_item = self._find_listing_item(candidate.source, candidate.source_job_id)
        if existing_item is not None:
            return self._update_existing_listing(existing_item, candidate, eligibility)

        merge_job_id, merge_matched_by = self._find_merge_match(keys)
        if merge_job_id is not None:
            return self._add_listing_to_job(merge_job_id, candidate, eligibility, keys, merge_matched_by)

        weak_candidate_job_id = self._find_weak_candidate(keys)
        return self._create_job(candidate, eligibility, keys, possible_duplicate_of=weak_candidate_job_id)

    def get_record(self, job_id: UUID) -> JobRecord | None:
        item = self._records.get_item(Key={"job_id": str(job_id)}, ConsistentRead=True).get("Item")
        return _item_to_record(item) if item else None

    def find_matches(self, keys: list[DedupKey]) -> list[DedupMatch]:
        matches: list[DedupMatch] = []
        for key in keys:
            job_id = self._lookup_dedup_key(key)
            if job_id is not None:
                matches.append(DedupMatch(job_id=job_id, matched_by=key.kind, matched_key=key.value))
        return matches

    def get_listing(self, source: SourceName, source_job_id: str) -> JobSourceListing | None:
        item = self._find_listing_item(source, source_job_id)
        return _item_to_listing(item) if item else None

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        items = _paginated(
            self._listings.query, KeyConditionExpression=Key("job_id").eq(str(job_id)), ConsistentRead=True
        )
        return [_item_to_listing(item) for item in items]

    def query(self, query: JobQuery) -> list[JobRecord]:
        # No GSI on eligibility_status -- a full scan at this data volume
        # (tens to hundreds of records) is simpler and cheaper than
        # maintaining an index, and it stays strongly consistent.
        items = _paginated(self._records.scan, ConsistentRead=True)
        if query.eligibility_status is not None:
            items = [item for item in items if item.get("eligibility_status") == query.eligibility_status.value]

        records = [_item_to_record(item) for item in items]

        if query.min_score is not None:
            records = [r for r in records if r.coarse_score is not None and r.coarse_score >= query.min_score]
        if query.source is not None:
            job_ids_for_source = {
                UUID(item["job_id"])
                for item in _paginated(self._listings.scan, ConsistentRead=True)
                if item.get("source") == query.source.value
            }
            records = [r for r in records if r.job_id in job_ids_for_source]

        return records[: query.limit]

    def record_score(self, job_id: UUID, score: CoarseScore, score_version: str) -> None:
        from botocore.exceptions import ClientError

        set_clauses = [
            "coarse_score = :cs",
            "coarse_score_reasoning = :cr",
            "score_model = :sm",
            "score_version = :sv",
            "scored_at = :sa",
            "updated_at = :ua",
        ]
        values: dict[str, Any] = {
            ":cs": score.score,
            ":cr": score.reasoning,
            ":sm": score.model,
            ":sv": score_version,
            ":sa": score.scored_at.isoformat(),
            ":ua": score.scored_at.isoformat(),
        }
        # Mirrors memory.py's record_score: only overwrite the JD-extracted
        # fields when Gemini actually returned them, so a scorer that omits
        # this part of the schema doesn't wipe a value set by an earlier run.
        if score.required_years_min is not None:
            set_clauses.append("required_years_min = :rym")
            values[":rym"] = score.required_years_min
        if score.required_years_max is not None:
            set_clauses.append("required_years_max = :ryx")
            values[":ryx"] = score.required_years_max
        if score.requirement_keywords:
            set_clauses.append("requirement_keywords = :rk")
            values[":rk"] = score.requirement_keywords

        try:
            self._records.update_item(
                Key={"job_id": str(job_id)},
                UpdateExpression="SET " + ", ".join(set_clauses),
                ConditionExpression="attribute_exists(job_id)",
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise KeyError(f"no JobRecord for {job_id}") from exc
            raise

    def _find_listing_item(self, source: SourceName, source_job_id: str) -> dict[str, Any] | None:
        """Two consistent primary-key reads, not a GSI query: source_lookup
        maps the (source, source_job_id) straight to a job_id, then the
        listing is fetched by its full composite key. See this module's
        docstring for why a GSI here caused a real production bug."""
        key = f"{source.value}#{source_job_id}"
        lookup = self._source_lookup.get_item(Key={"source_job_id_key": key}, ConsistentRead=True).get("Item")
        if lookup is None:
            return None
        return self._listings.get_item(
            Key={"job_id": lookup["job_id"], "source_job_id_key": key}, ConsistentRead=True
        ).get("Item")

    def _lookup_dedup_key(self, key: DedupKey) -> UUID | None:
        item = self._dedup_keys.get_item(
            Key={"key": f"{key.kind.value}#{key.value}"}, ConsistentRead=True
        ).get("Item")
        return UUID(item["job_id"]) if item else None

    def _find_merge_match(self, keys: list[DedupKey]) -> tuple[UUID | None, DedupKeyKind | None]:
        for kind in self._MERGE_KEY_KINDS:
            key = next((k for k in keys if k.kind is kind), None)
            if key is None:
                continue
            job_id = self._lookup_dedup_key(key)
            if job_id is not None:
                return job_id, key.kind
        return None, None

    def _find_weak_candidate(self, keys: list[DedupKey]) -> UUID | None:
        key = next((k for k in keys if k.kind is DedupKeyKind.COMPANY_TITLE_LOCATION), None)
        if key is None:
            return None
        return self._lookup_dedup_key(key)

    def _update_existing_listing(
        self, listing_item: dict[str, Any], candidate: NormalizedJobCandidate, eligibility: EligibilityDecision
    ) -> UpsertResult:
        job_id = UUID(listing_item["job_id"])
        listing = _item_to_listing(listing_item)

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
        self._listings.put_item(Item=_listing_to_item(listing))

        job = self.get_record(job_id)
        assert job is not None
        changed = self._refresh_record_fields(job, candidate, eligibility)
        if changed:
            job.updated_at = candidate.observed_at
            self._records.put_item(Item=_record_to_item(job))

        status = UpsertStatus.LISTING_UPDATED if changed else UpsertStatus.LISTING_UNCHANGED
        return UpsertResult(
            status=status, job_id=job_id, listing_id=listing.listing_id, matched_by=DedupKeyKind.SOURCE_ID
        )

    def _add_listing_to_job(
        self,
        job_id: UUID,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
        matched_by: DedupKeyKind | None,
    ) -> UpsertResult:
        job = self.get_record(job_id)
        assert job is not None
        self._refresh_record_fields(job, candidate, eligibility)
        job.updated_at = candidate.observed_at
        self._records.put_item(Item=_record_to_item(job))

        listing = self._new_listing(job_id, candidate)
        self._listings.put_item(Item=_listing_to_item(listing))
        self._register_source_lookup(listing)
        self._register_keys(keys, job_id)

        return UpsertResult(status=UpsertStatus.LISTING_ADDED, job_id=job_id, listing_id=listing.listing_id, matched_by=matched_by)

    def _create_job(
        self,
        candidate: NormalizedJobCandidate,
        eligibility: EligibilityDecision,
        keys: list[DedupKey],
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
            possible_duplicate_of=possible_duplicate_of,
            duplicate_matched_by=DedupKeyKind.COMPANY_TITLE_LOCATION if possible_duplicate_of else None,
            eligibility_status=eligibility.status,
            filter_codes=eligibility.codes,
            filter_version=eligibility.filter_version,
            created_at=candidate.observed_at,
            updated_at=candidate.observed_at,
        )
        self._records.put_item(Item=_record_to_item(job))

        listing = self._new_listing(job.job_id, candidate)
        self._listings.put_item(Item=_listing_to_item(listing))
        self._register_source_lookup(listing)
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

    def _register_source_lookup(self, listing: JobSourceListing) -> None:
        key = f"{listing.source.value}#{listing.source_job_id}"
        self._source_lookup.put_item(Item={"source_job_id_key": key, "job_id": str(listing.job_id)})

    def _register_keys(self, keys: list[DedupKey], job_id: UUID) -> None:
        from botocore.exceptions import ClientError

        for key in keys:
            try:
                self._dedup_keys.put_item(
                    Item={"key": f"{key.kind.value}#{key.value}", "job_id": str(job_id)},
                    ConditionExpression="attribute_not_exists(#k)",
                    ExpressionAttributeNames={"#k": "key"},
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                # another job already claimed this key first -- leave it,
                # matches memory.py's dict.setdefault semantics
