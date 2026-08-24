from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from typing import Any

import boto3

from job_discovery.maintenance.reclassify_years import has_years_change, reclassify_years_item
from job_discovery.repositories.dynamodb import _paginated


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-extract job experience requirements and eligibility")
    parser.add_argument("--records-table", default=os.environ.get("RECORDS_TABLE"))
    parser.add_argument("--max-years", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="Write changes; without this flag the command is dry-run")
    args = parser.parse_args()
    if not args.records_table:
        parser.error("--records-table or RECORDS_TABLE is required")

    table = boto3.resource("dynamodb").Table(args.records_table)
    items = _paginated(table.scan, ConsistentRead=True)
    changes: list[tuple[dict[str, Any], Any]] = []
    statuses: Counter[str] = Counter()
    for item in items:
        result = reclassify_years_item(item, args.max_years)
        statuses[result.eligibility_status] += 1
        if has_years_change(item, result):
            changes.append((item, result))

    if args.apply:
        for item, result in changes:
            _apply(table, item["job_id"], result, args.max_years)

    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run",
        "records_table": args.records_table,
        "max_years": args.max_years,
        "scanned": len(items),
        "changed": len(changes),
        "resulting_statuses": dict(statuses),
        "sample_job_ids": [str(item["job_id"]) for item, _ in changes[:20]],
    }, indent=2))


def _apply(table: Any, job_id: str, result: Any, max_years: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    set_parts = [
        "years_mentioned = :mentioned", "filter_codes = :codes", "eligibility_status = :status",
        "filter_version = :version", "updated_at = :updated",
    ]
    remove_parts: list[str] = []
    values: dict[str, Any] = {
        ":mentioned": result.mentioned,
        ":codes": result.filter_codes,
        ":status": result.eligibility_status,
        ":version": f"years-backfill-max-{max_years}",
        ":updated": now,
    }
    for field, value, token in (
        ("required_years_min", result.minimum, ":minimum"),
        ("required_years_max", result.maximum, ":maximum"),
    ):
        if value is None:
            remove_parts.append(field)
        else:
            set_parts.append(f"{field} = {token}")
            values[token] = value
    expression = "SET " + ", ".join(set_parts)
    if remove_parts:
        expression += " REMOVE " + ", ".join(remove_parts)
    table.update_item(
        Key={"job_id": str(job_id)},
        UpdateExpression=expression,
        ExpressionAttributeValues=values,
    )


if __name__ == "__main__":
    main()
