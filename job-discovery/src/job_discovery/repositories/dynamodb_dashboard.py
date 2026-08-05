from __future__ import annotations

from typing import Any
from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Key

from job_discovery.dashboard.interfaces import DashboardJobReader
from job_discovery.domain.models import JobRecord, JobSourceListing
from job_discovery.repositories.dynamodb import _item_to_listing, _item_to_record, _paginated


class DynamoDBDashboardJobReader(DashboardJobReader):
    def __init__(self, records_table: str, listings_table: str, resource: Any = None) -> None:
        dynamodb = resource or boto3.resource("dynamodb")
        self._records = dynamodb.Table(records_table)
        self._listings = dynamodb.Table(listings_table)

    def list_records(self) -> list[JobRecord]:
        items = _paginated(self._records.scan, ConsistentRead=True)
        return [_item_to_record(item) for item in items]

    def list_all_listings(self) -> list[JobSourceListing]:
        items = _paginated(self._listings.scan, ConsistentRead=True)
        return [_item_to_listing(item) for item in items]

    def get_record(self, job_id: UUID) -> JobRecord | None:
        item = self._records.get_item(Key={"job_id": str(job_id)}, ConsistentRead=True).get("Item")
        return _item_to_record(item) if item else None

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        items = _paginated(
            self._listings.query,
            KeyConditionExpression=Key("job_id").eq(str(job_id)),
            ConsistentRead=True,
        )
        return [_item_to_listing(item) for item in items]
