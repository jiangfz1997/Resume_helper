"""Plan and execute removal of every listing from one source.

The planner is intentionally read-only.  Execution consumes the exact plan,
so callers can print and back it up before making any changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from boto3.dynamodb.conditions import Key


def _paginated(operation: Any, **kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    response = operation(**kwargs)
    items.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey"):
        response = operation(ExclusiveStartKey=response["LastEvaluatedKey"], **kwargs)
        items.extend(response.get("Items", []))
    return items


@dataclass(frozen=True)
class SourceCleanupPlan:
    source: str
    listings: list[dict[str, Any]]
    source_lookups: list[dict[str, Any]]
    dedup_keys: list[dict[str, Any]]
    records: list[dict[str, Any]]
    user_states: list[dict[str, Any]]
    preserved_job_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "counts": {
                "listings": len(self.listings),
                "source_lookups": len(self.source_lookups),
                "dedup_keys": len(self.dedup_keys),
                "records": len(self.records),
                "user_states": len(self.user_states),
                "jobs_preserved_with_other_sources": len(self.preserved_job_ids),
            },
            "listings": self.listings,
            "source_lookups": self.source_lookups,
            "dedup_keys": self.dedup_keys,
            "records": self.records,
            "user_states": self.user_states,
            "preserved_job_ids": self.preserved_job_ids,
        }


def build_source_cleanup_plan(
    resource: Any,
    *,
    source: str,
    records_table: str,
    listings_table: str,
    dedup_keys_table: str,
    source_lookup_table: str,
    user_data_table: str | None = None,
) -> SourceCleanupPlan:
    """Return everything that must be removed, without writing to DynamoDB."""
    records = resource.Table(records_table)
    listings = resource.Table(listings_table)
    dedup_keys = resource.Table(dedup_keys_table)
    source_lookup = resource.Table(source_lookup_table)

    target_listings = [item for item in _paginated(listings.scan, ConsistentRead=True) if item.get("source") == source]
    targets_by_job: dict[str, list[dict[str, Any]]] = {}
    for listing in target_listings:
        targets_by_job.setdefault(listing["job_id"], []).append(listing)

    deleted_job_ids: set[str] = set()
    preserved_job_ids: list[str] = []
    for job_id, targets in targets_by_job.items():
        all_job_listings = _paginated(
            listings.query,
            KeyConditionExpression=Key("job_id").eq(job_id),
            ConsistentRead=True,
        )
        if len(all_job_listings) == len(targets):
            deleted_job_ids.add(job_id)
        else:
            preserved_job_ids.append(job_id)

    record_items: list[dict[str, Any]] = []
    for job_id in sorted(deleted_job_ids):
        item = records.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
        if item:
            record_items.append(item)

    lookup_items: list[dict[str, Any]] = []
    source_dedup_owners: dict[str, str] = {}
    for listing in target_listings:
        lookup_key = listing["source_job_id_key"]
        lookup = source_lookup.get_item(
            Key={"source_job_id_key": lookup_key}, ConsistentRead=True
        ).get("Item")
        if lookup:
            lookup_items.append(lookup)
        dedup_key = f"source_id#{source}:{listing['source_job_id']}"
        source_dedup_owners[dedup_key] = listing["job_id"]

    dedup_items = []
    for item in _paginated(dedup_keys.scan, ConsistentRead=True):
        job_id = item.get("job_id")
        if job_id in deleted_job_ids:
            dedup_items.append(item)
        elif source_dedup_owners.get(item.get("key")) == job_id:
            # For a shared JobRecord, only SOURCE_ID is provably owned by the
            # removed listing. Other keys can also belong to a retained source.
            dedup_items.append(item)

    user_state_items: list[dict[str, Any]] = []
    if user_data_table and deleted_job_ids:
        user_states = resource.Table(user_data_table)
        user_state_items = [
            item
            for item in _paginated(user_states.scan, ConsistentRead=True)
            if item.get("job_id") in deleted_job_ids
        ]

    return SourceCleanupPlan(
        source=source,
        listings=target_listings,
        source_lookups=lookup_items,
        dedup_keys=dedup_items,
        records=record_items,
        user_states=user_state_items,
        preserved_job_ids=sorted(preserved_job_ids),
    )


def execute_source_cleanup_plan(
    resource: Any,
    plan: SourceCleanupPlan,
    *,
    records_table: str,
    listings_table: str,
    dedup_keys_table: str,
    source_lookup_table: str,
    user_data_table: str | None = None,
) -> None:
    """Delete the exact items captured in a previously reviewed plan."""
    with resource.Table(source_lookup_table).batch_writer() as batch:
        for item in plan.source_lookups:
            batch.delete_item(Key={"source_job_id_key": item["source_job_id_key"]})
    with resource.Table(listings_table).batch_writer() as batch:
        for item in plan.listings:
            batch.delete_item(Key={"job_id": item["job_id"], "source_job_id_key": item["source_job_id_key"]})
    with resource.Table(dedup_keys_table).batch_writer() as batch:
        for item in plan.dedup_keys:
            batch.delete_item(Key={"key": item["key"]})
    if user_data_table:
        with resource.Table(user_data_table).batch_writer() as batch:
            for item in plan.user_states:
                batch.delete_item(Key={"user_id": item["user_id"], "entity_key": item["entity_key"]})
    with resource.Table(records_table).batch_writer() as batch:
        for item in plan.records:
            batch.delete_item(Key={"job_id": item["job_id"]})
