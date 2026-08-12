"""Dry-run or remove one complete job source from DynamoDB.

Example (preview only):

    PYTHONPATH=src python scripts/cleanup_source.py

Execution requires both an explicit confirmation and a backup path:

    PYTHONPATH=src python scripts/cleanup_source.py \
      --execute --confirm-source simplify_github \
      --backup simplify-github-backup.json
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3

from job_discovery.maintenance.cleanup_source import build_source_cleanup_plan, execute_source_cleanup_plan


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove all listings belonging to one DynamoDB job source")
    parser.add_argument("--source", default="simplify_github")
    parser.add_argument("--records-table", default="job-discovery-records")
    parser.add_argument("--listings-table", default="job-discovery-listings")
    parser.add_argument("--dedup-keys-table", default="job-discovery-dedup-keys")
    parser.add_argument("--source-lookup-table", default="job-discovery-source-lookup")
    parser.add_argument("--user-data-table", default="job-discovery-user-data")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-source", help="must exactly equal --source when using --execute")
    parser.add_argument("--backup", type=Path, help="required JSON backup destination when using --execute")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region) if args.profile else boto3.Session(region_name=args.region)
    resource = session.resource("dynamodb")
    table_args = {
        "records_table": args.records_table,
        "listings_table": args.listings_table,
        "dedup_keys_table": args.dedup_keys_table,
        "source_lookup_table": args.source_lookup_table,
        "user_data_table": args.user_data_table,
    }
    plan = build_source_cleanup_plan(resource, source=args.source, **table_args)
    payload = plan.as_dict()
    print(json.dumps({"source": args.source, "counts": payload["counts"]}, indent=2, default=_json_default))

    if not args.execute:
        print("DRY RUN ONLY: no data was deleted")
        return
    if args.confirm_source != args.source:
        parser.error("--confirm-source must exactly equal --source")
    if args.backup is None:
        parser.error("--backup is required with --execute")
    if args.backup.exists():
        parser.error(f"backup already exists: {args.backup}")

    # Exclusive creation prevents accidentally overwriting an earlier backup.
    with args.backup.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=_json_default)
        handle.write("\n")
    execute_source_cleanup_plan(resource, plan, **table_args)
    print(f"deleted source {args.source}; backup written to {args.backup}")


if __name__ == "__main__":
    main()
