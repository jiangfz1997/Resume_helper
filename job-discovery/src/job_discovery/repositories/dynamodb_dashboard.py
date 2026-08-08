"""Read-only DynamoDB access for the dashboard.

The two list_* methods Scan whole tables, so they project only the
attributes dashboard/service.py actually reads (_to_summary,
list_dashboard_runs, get_scoring_queue). JobRecord.description and
coarse_score_reasoning are multi-KB blobs that no list view renders;
fetching them pushed every Scan through several 1MB pages.

Consequence: records and listings returned by list_records() and
list_all_listings() carry None for every attribute not in the tuples below,
whatever is actually stored. Adding a field to _to_summary means adding it
here too, or it silently arrives as None. The detail path (get_record,
list_listings) is deliberately left unprojected -- DashboardJobDetail does
render description, and _to_listing reads posted_at_raw.

ConsistentRead is not used here. dynamodb.py needs it because it writes and
immediately reads back; this reader only reads tables it never writes, so
eventually consistent reads are correct and cost half the RCU.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Key

from job_discovery.dashboard.interfaces import DashboardJobReader
from job_discovery.domain.models import JobRecord, JobSourceListing
from job_discovery.repositories.dynamodb import _item_to_listing, _item_to_record, _paginated

_RECORD_SUMMARY_FIELDS = (
    "job_id",
    "canonical_title",
    "canonical_company",
    "canonical_location",
    "workplace_type",
    "job_category",
    "salary_text",
    "description_chars",
    "required_years_min",
    "required_years_max",
    "requirement_keywords",
    "eligibility_status",
    "filter_codes",
    "coarse_score",
    "first_discovered_run_id",
    "created_at",
    "updated_at",
)

_LISTING_SUMMARY_FIELDS = (
    "listing_id",
    "job_id",
    "source",
    "source_job_id",
    "source_url",
    "apply_url_canonical",
    "posted_at",
    "posted_at_quality",
    "first_seen_at",
    "last_seen_at",
    "last_seen_run_id",
    "status",
)


def _projection(fields: tuple[str, ...]) -> dict[str, Any]:
    """Aliases every attribute, so reserved words (source, status) never
    need special-casing."""
    names = {f"#p{index}": field for index, field in enumerate(fields)}
    return {"ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names}


class DynamoDBDashboardJobReader(DashboardJobReader):
    def __init__(self, records_table: str, listings_table: str, resource: Any = None) -> None:
        dynamodb = resource or boto3.resource("dynamodb")
        self._records = dynamodb.Table(records_table)
        self._listings = dynamodb.Table(listings_table)

    def list_records(self) -> list[JobRecord]:
        items = _paginated(self._records.scan, **_projection(_RECORD_SUMMARY_FIELDS))
        return [_item_to_record(item) for item in items]

    def list_all_listings(self) -> list[JobSourceListing]:
        items = _paginated(self._listings.scan, **_projection(_LISTING_SUMMARY_FIELDS))
        return [_item_to_listing(item) for item in items]

    def get_record(self, job_id: UUID) -> JobRecord | None:
        item = self._records.get_item(Key={"job_id": str(job_id)}).get("Item")
        return _item_to_record(item) if item else None

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        items = _paginated(self._listings.query, KeyConditionExpression=Key("job_id").eq(str(job_id)))
        return [_item_to_listing(item) for item in items]
