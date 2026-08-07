from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from pydantic import ValidationError

from candidate_profile.domain.models import (
    ApplicationStatus,
    CandidateProfileInput,
    CreateApplicationFromJob,
    CreateApplicationFromUrl,
    UpdateApplicationFields,
    UpdateApplicationStatus,
)
from candidate_profile.repositories.dynamodb import DynamoDBCandidateProfileRepository

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

_repository: DynamoDBCandidateProfileRepository | None = None
_lambda_client: Any = None


def _get_repository() -> DynamoDBCandidateProfileRepository:
    global _repository
    if _repository is None:
        _repository = DynamoDBCandidateProfileRepository(os.environ["TABLE_NAME"])
    return _repository


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    claims = _claims(event)
    if os.environ.get("REQUIRE_AUTH", "true").casefold() == "true" and not claims:
        return _response(401, {"detail": "authentication required"})
    user_id = str(claims.get("sub", "local-user"))
    repository = _get_repository()

    route_key = event.get("routeKey", "")
    try:
        if route_key == "GET /profile":
            profile = repository.get_profile(user_id)
            return _response(200, {"profile": profile.model_dump(mode="json") if profile else None})
        if route_key == "PUT /profile":
            request = CandidateProfileInput.model_validate_json(event.get("body") or "{}")
            profile = repository.save_profile(user_id, request)
            return _response(200, profile.model_dump(mode="json"))

        if route_key == "POST /applications/from-job":
            request = CreateApplicationFromJob.model_validate_json(event.get("body") or "{}")
            application = repository.create_application_from_job(user_id, request)
            return _response(201, application.model_dump(mode="json"))

        if route_key == "POST /applications/from-url":
            request = CreateApplicationFromUrl.model_validate_json(event.get("body") or "{}")
            application = repository.create_application_pending(user_id, request.url)
            _invoke_extraction(user_id, application.application_id, request.url)
            return _response(202, application.model_dump(mode="json"))

        if route_key == "GET /applications":
            status_param = (event.get("queryStringParameters") or {}).get("status")
            status = ApplicationStatus(status_param) if status_param else None
            applications = repository.list_applications(user_id, status)
            return _response(200, {"items": [application.model_dump(mode="json") for application in applications]})

        if route_key == "GET /applications/stats":
            stats = repository.get_application_stats(user_id)
            return _response(200, stats.model_dump(mode="json"))

        if route_key == "GET /applications/{application_id}":
            application_id = (event.get("pathParameters") or {}).get("application_id", "")
            application = repository.get_application(user_id, application_id)
            if application is None:
                return _response(404, {"detail": "application not found"})
            return _response(200, application.model_dump(mode="json"))

        if route_key == "PATCH /applications/{application_id}/status":
            application_id = (event.get("pathParameters") or {}).get("application_id", "")
            request = UpdateApplicationStatus.model_validate_json(event.get("body") or "{}")
            application = repository.update_application_status(user_id, application_id, request.status, request.note)
            if application is None:
                return _response(404, {"detail": "application not found"})
            return _response(200, application.model_dump(mode="json"))

        if route_key == "PATCH /applications/{application_id}":
            application_id = (event.get("pathParameters") or {}).get("application_id", "")
            request = UpdateApplicationFields.model_validate_json(event.get("body") or "{}")
            application = repository.update_application_fields(user_id, application_id, request)
            if application is None:
                return _response(404, {"detail": "application not found"})
            return _response(200, application.model_dump(mode="json"))

        if route_key == "DELETE /applications/{application_id}":
            application_id = (event.get("pathParameters") or {}).get("application_id", "")
            repository.delete_application(user_id, application_id)
            return _response(200, {"ok": True})
    except (ValidationError, ValueError) as exc:
        return _response(400, {"detail": str(exc)[:500]})
    except Exception:
        log.exception("candidate-profile request failed")
        return _response(500, {"detail": "internal server error"})

    return _response(404, {"detail": "route not found"})


def _invoke_extraction(user_id: str, application_id: str, url: str) -> None:
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    _lambda_client.invoke(
        FunctionName=os.environ["EXTRACT_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"user_id": user_id, "application_id": application_id, "url": url}).encode("utf-8"),
    )


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
    }
    allowed_origin = os.environ.get("ALLOWED_ORIGIN")
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":")),
    }
