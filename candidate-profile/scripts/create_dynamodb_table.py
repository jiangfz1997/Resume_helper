"""One-time provisioning: create the candidate-profile DynamoDB table.

Safe to re-run: create_table() only creates the table if it does not already
exist.

    PYTHONPATH=src python scripts/create_dynamodb_table.py \\
        --table candidate-profile-data \\
        --region us-east-1
"""

from __future__ import annotations

import argparse

import boto3

from candidate_profile.repositories.schema import create_table


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the candidate-profile DynamoDB table")
    parser.add_argument("--table", default="candidate-profile-data")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    resource = boto3.resource("dynamodb", region_name=args.region)
    print(f"ensuring {args.table} exists in {args.region}...")
    create_table(resource, args.table)
    print("done. billing mode: PAY_PER_REQUEST (on-demand, no idle cost).")


if __name__ == "__main__":
    main()
