from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

from job_discovery.application.personalized_score import score_jobs_for_users
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository
from job_discovery.repositories.factory import build_repository
from job_discovery.scoring.gemini_scorer import GeminiCoarseScorer

log = logging.getLogger()
log.setLevel(logging.INFO)

PROMPT_VERSION = "personalized-v1"


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    del context
    event = event or {}
    repository, repository_backend = build_repository()
    user_data = DynamoDBDashboardUserStateRepository(os.environ["USER_DATA_TABLE"])
    profiles = [profile for profile in user_data.list_scoring_profiles() if profile.active]
    if not profiles:
        return {"repository_backend": repository_backend, "active_profiles": 0, "scored": 0, "errors": 0}

    scorer = GeminiCoarseScorer()
    scored, errors = score_jobs_for_users(
        repository,
        user_data,
        scorer,
        prompt_version=PROMPT_VERSION,
        limit=int(event.get("limit", 100)),
        user_ids=set(event["user_ids"]) if event.get("user_ids") else None,
        job_ids={UUID(value) for value in event["job_ids"]} if event.get("job_ids") else None,
    )
    response = {
        "repository_backend": repository_backend,
        "active_profiles": len(profiles),
        "scored": scored,
        "errors": errors,
    }
    log.info("personalized scoring complete: %s", response)
    return response


if __name__ == "__main__":
    import sys

    cli_event = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(lambda_handler(cli_event, None), indent=2))
