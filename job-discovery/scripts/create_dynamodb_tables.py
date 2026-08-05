"""One-time provisioning: create the four real DynamoDB tables.

Safe to re-run: create_tables() only creates whatever doesn't already exist,
so running this again after the schema grew a table (records/listings/
dedup-keys -> +source-lookup, see dynamodb_schema.py's module docstring for
why) just adds the missing one.

Uses the same schema definitions the moto contract tests validate against
(repositories/dynamodb_schema.py), so this cannot silently drift from what
the tests already proved correct.

Requires AWS credentials in the environment (aws configure, or
AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN) with permission to
create DynamoDB tables.

    PYTHONPATH=src python scripts/create_dynamodb_tables.py \\
        --records-table job-discovery-records \\
        --listings-table job-discovery-listings \\
        --dedup-keys-table job-discovery-dedup-keys \\
        --source-lookup-table job-discovery-source-lookup \\
        --region us-east-1
"""

from __future__ import annotations

import argparse

import boto3

from job_discovery.repositories.dynamodb_schema import create_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the job-discovery DynamoDB tables")
    parser.add_argument("--records-table", default="job-discovery-records")
    parser.add_argument("--listings-table", default="job-discovery-listings")
    parser.add_argument("--dedup-keys-table", default="job-discovery-dedup-keys")
    parser.add_argument("--source-lookup-table", default="job-discovery-source-lookup")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    resource = boto3.resource("dynamodb", region_name=args.region)

    print(
        f"ensuring {args.records_table}, {args.listings_table}, "
        f"{args.dedup_keys_table}, {args.source_lookup_table} exist in {args.region}..."
    )
    create_tables(resource, args.records_table, args.listings_table, args.dedup_keys_table, args.source_lookup_table)
    print("done. billing mode: PAY_PER_REQUEST (on-demand, no idle cost).")


if __name__ == "__main__":
    main()
