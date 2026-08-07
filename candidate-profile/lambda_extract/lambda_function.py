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
from candidate_profile.extraction.fetcher import HttpPageFetcher, html_to_text, strip_non_content_tags
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
        html = HttpPageFetcher().fetch(url)
        page_text = html_to_text(html)
        if not page_text.strip():
            raise ValueError("no extractable text found on page")
        page_text = page_text[:MAX_JD_TEXT_CHARS]
        extracted = GeminiJobInfoExtractor().extract(page_text)
        repository.complete_application_extraction(
            user_id, application_id, extracted, strip_non_content_tags(html)
        )
        return {"ok": True}
    except Exception as exc:
        log.exception("application extraction failed: user=%s application=%s url=%s", user_id, application_id, url)
        repository.fail_application_extraction(user_id, application_id, str(exc))
        return {"ok": False, "error": str(exc)}
