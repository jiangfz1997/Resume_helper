"""Builds the JobRepository a Lambda handler should use, from environment
variables. Falls back to InMemoryJobRepository when the DynamoDB table names
aren't configured, so a crawler Lambda still runs with zero extra AWS setup
-- the same optionality pattern GeminiCoarseScorer uses for
GEMINI_API_KEY/GEMINI_MODEL.

RECORDS_TABLE, LISTINGS_TABLE, DEDUP_KEYS_TABLE and SOURCE_LOOKUP_TABLE must
be set together. Partial configuration is treated as a startup error, not a
fallback: a repository silently backed by only some of the four tables would
fail unpredictably mid-run instead of failing loudly before anything runs.
"""

from __future__ import annotations

import os

from job_discovery.domain.interfaces import JobRepository

_ENV_VARS = ("RECORDS_TABLE", "LISTINGS_TABLE", "DEDUP_KEYS_TABLE", "SOURCE_LOOKUP_TABLE")


def build_repository() -> tuple[JobRepository, str]:
    values = {name: os.environ.get(name) for name in _ENV_VARS}

    if not any(values.values()):
        from job_discovery.repositories.memory import InMemoryJobRepository

        return InMemoryJobRepository(), "memory"

    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"partial DynamoDB config: missing {missing}; set all three table env vars or none")

    from job_discovery.repositories.dynamodb import DynamoDBJobRepository

    return (
        DynamoDBJobRepository(
            values["RECORDS_TABLE"],
            values["LISTINGS_TABLE"],
            values["DEDUP_KEYS_TABLE"],
            values["SOURCE_LOOKUP_TABLE"],
        ),
        "dynamodb",
    )
