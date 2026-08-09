"""Async worker invoked fire-and-forget by lambda_api's POST
/applications/from-url, same pattern as job-discovery's lambda_scoring: the
synchronous API call only writes a pending record, this Lambda does the
slow part (fetch + LLM extraction) and writes the result back, so the API
response never risks hitting API Gateway's 29s timeout.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from candidate_profile.extraction.extractor import GeminiJobInfoExtractor
from candidate_profile.extraction.fetcher import CompositePageFetcher
from candidate_profile.repositories.dynamodb import DynamoDBCandidateProfileRepository

log = logging.getLogger()
log.setLevel(logging.INFO)

MAX_JD_TEXT_CHARS = 20_000

_repository: DynamoDBCandidateProfileRepository | None = None


def _get_repository() -> DynamoDBCandidateProfileRepository:
    global _repository
    if _repository is None:
        _repository = DynamoDBCandidateProfileRepository(os.environ["TABLE_NAME"])
    return _repository


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    user_id = event["user_id"]
    application_id = event["application_id"]
    url = event["url"]
    repository = _get_repository()

    try:
        page = CompositePageFetcher().load(url)
        if not page.text.strip():
            raise ValueError("no extractable text found on page")
        log.info("fetched %s via %s (%d chars)", url, page.fetch_strategy.value, len(page.text))
        extracted = GeminiJobInfoExtractor().extract(page.text[:MAX_JD_TEXT_CHARS])
        repository.complete_application_extraction(user_id, application_id, extracted, page.raw_html)
        return {"ok": True}
    except Exception as exc:
        log.exception("application extraction failed: user=%s application=%s url=%s", user_id, application_id, url)
        repository.fail_application_extraction(user_id, application_id, str(exc))
        return {"ok": False, "error": str(exc)}
