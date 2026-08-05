"""Table definitions shared between real infrastructure provisioning
(scripts/create_dynamodb_tables.py) and the moto-backed contract tests in
tests/unit/test_repository_contract.py, so the two can never drift apart.

Four tables, every read a primary-key read with ConsistentRead=True, zero
GSIs. This is a correction, not the original design: an earlier version used
two GSIs (source lookup, eligibility_status) to avoid a table scan, and a
real Lambda run on 2026-08-05 hit an AssertionError because GSI reads are
*always* eventually consistent in DynamoDB -- there is no ConsistentRead
option for a GSI, unlike the base table. Code had just written a new listing
and immediately queried it back through the GSI before replication caught
up. moto's DynamoDB mock cannot reproduce this: it is a single in-process
dict with no real replication lag, so no contract test run against moto
could have caught it -- only a real AWS account exhibits this behavior.

At this project's data volume (tens to hundreds of records) a full table
Scan with ConsistentRead=True, filtered in Python, is simpler and cheaper
than maintaining a GSI, and it sidesteps the whole consistency class of bug.
"""

from __future__ import annotations

from typing import Any

RECORDS_KEY_SCHEMA = [{"AttributeName": "job_id", "KeyType": "HASH"}]
RECORDS_ATTRIBUTE_DEFINITIONS = [{"AttributeName": "job_id", "AttributeType": "S"}]

# SK is source#source_job_id so Query(PK=job_id) returns every listing for a
# job in one call.
LISTINGS_KEY_SCHEMA = [
    {"AttributeName": "job_id", "KeyType": "HASH"},
    {"AttributeName": "source_job_id_key", "KeyType": "RANGE"},
]
LISTINGS_ATTRIBUTE_DEFINITIONS = [
    {"AttributeName": "job_id", "AttributeType": "S"},
    {"AttributeName": "source_job_id_key", "AttributeType": "S"},
]

DEDUP_KEYS_KEY_SCHEMA = [{"AttributeName": "key", "KeyType": "HASH"}]
DEDUP_KEYS_ATTRIBUTE_DEFINITIONS = [{"AttributeName": "key", "AttributeType": "S"}]

# Maps a (source, source_job_id) straight to job_id. Exists specifically so
# "have we already seen this exact listing" can be answered with a
# ConsistentRead=True GetItem instead of a GSI query.
SOURCE_LOOKUP_KEY_SCHEMA = [{"AttributeName": "source_job_id_key", "KeyType": "HASH"}]
SOURCE_LOOKUP_ATTRIBUTE_DEFINITIONS = [{"AttributeName": "source_job_id_key", "AttributeType": "S"}]


def create_tables(
    resource: Any,
    records_table: str,
    listings_table: str,
    dedup_keys_table: str,
    source_lookup_table: str,
) -> None:
    """Only creates tables that do not already exist, so re-running this
    after adding a new table (as happened going from 3 tables to 4) does not
    require deleting and recreating the ones already provisioned."""
    existing = {t.name for t in resource.tables.all()}

    to_create = [
        (records_table, RECORDS_KEY_SCHEMA, RECORDS_ATTRIBUTE_DEFINITIONS),
        (listings_table, LISTINGS_KEY_SCHEMA, LISTINGS_ATTRIBUTE_DEFINITIONS),
        (dedup_keys_table, DEDUP_KEYS_KEY_SCHEMA, DEDUP_KEYS_ATTRIBUTE_DEFINITIONS),
        (source_lookup_table, SOURCE_LOOKUP_KEY_SCHEMA, SOURCE_LOOKUP_ATTRIBUTE_DEFINITIONS),
    ]

    created = []
    for table_name, key_schema, attribute_definitions in to_create:
        if table_name in existing:
            continue
        resource.create_table(
            TableName=table_name,
            KeySchema=key_schema,
            AttributeDefinitions=attribute_definitions,
            BillingMode="PAY_PER_REQUEST",
        )
        created.append(table_name)

    for table_name in created:
        resource.Table(table_name).wait_until_exists()
