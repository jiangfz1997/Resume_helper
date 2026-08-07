from __future__ import annotations

from typing import Any

KEY_SCHEMA = [
    {"AttributeName": "user_id", "KeyType": "HASH"},
    {"AttributeName": "entity_key", "KeyType": "RANGE"},
]
ATTRIBUTE_DEFINITIONS = [
    {"AttributeName": "user_id", "AttributeType": "S"},
    {"AttributeName": "entity_key", "AttributeType": "S"},
]


def create_table(resource: Any, table_name: str) -> None:
    existing = {table.name for table in resource.tables.all()}
    if table_name in existing:
        return
    table = resource.create_table(
        TableName=table_name,
        KeySchema=KEY_SCHEMA,
        AttributeDefinitions=ATTRIBUTE_DEFINITIONS,
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
