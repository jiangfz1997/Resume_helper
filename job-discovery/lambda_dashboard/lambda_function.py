from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from job_discovery.dashboard.interfaces import DashboardJobReader, DashboardUserStateRepository
from job_discovery.dashboard.models import DashboardJobQuery, UpdateJobStateRequest
from job_discovery.dashboard.service import get_dashboard_job, list_dashboard_jobs, list_dashboard_runs
from job_discovery.domain.settings import DiscoverySettingsInput, ScoringProfileInput
from job_discovery.repositories.dynamodb_dashboard import DynamoDBDashboardJobReader
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

_reader: DashboardJobReader | None = None
_state_repository: DashboardUserStateRepository | None = None


def _get_reader() -> DashboardJobReader:
    global _reader
    if _reader is None:
        _reader = DynamoDBDashboardJobReader(
            records_table=os.environ["RECORDS_TABLE"],
            listings_table=os.environ["LISTINGS_TABLE"],
        )
    return _reader


def _get_state_repository() -> DashboardUserStateRepository:
    global _state_repository
    if _state_repository is None:
        _state_repository = DynamoDBDashboardUserStateRepository(os.environ["USER_DATA_TABLE"])
    return _state_repository


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    claims = _claims(event)
    if os.environ.get("REQUIRE_AUTH", "true").casefold() == "true" and not claims:
        return _response(401, {"detail": "authentication required"})
    user_id = str(claims.get("sub", "local-user"))

    route_key = event.get("routeKey", "")
    try:
        if route_key == "GET /jobs":
            query = _parse_query(event.get("queryStringParameters"))
            return _response(200, list_dashboard_jobs(_get_reader(), query).model_dump(mode="json"))
        if route_key == "GET /jobs/{job_id}":
            job_id = UUID((event.get("pathParameters") or {}).get("job_id", ""))
            job = get_dashboard_job(_get_reader(), job_id)
            if job is None:
                return _response(404, {"detail": "job not found"})
            return _response(200, job.model_dump(mode="json"))
        if route_key == "GET /runs":
            return _response(200, list_dashboard_runs(_get_reader()).model_dump(mode="json"))
        if route_key == "GET /user-state":
            return _response(200, _get_state_repository().get_snapshot(user_id).model_dump(mode="json"))
        if route_key == "PUT /jobs/{job_id}/viewed":
            job_id = UUID((event.get("pathParameters") or {}).get("job_id", ""))
            _get_state_repository().mark_job_viewed(user_id, job_id)
            return _response(200, {"ok": True})
        if route_key == "PUT /jobs/{job_id}/state":
            job_id = UUID((event.get("pathParameters") or {}).get("job_id", ""))
            request = UpdateJobStateRequest.model_validate_json(event.get("body") or "{}")
            _get_state_repository().set_job_status(user_id, job_id, request.status)
            return _response(200, {"ok": True})
        if route_key == "PUT /runs/{run_id}/viewed":
            run_id = (event.get("pathParameters") or {}).get("run_id", "").strip()
            if not run_id:
                raise ValueError("run_id is required")
            _get_state_repository().mark_run_viewed(user_id, run_id)
            return _response(200, {"ok": True})
        if route_key == "GET /profile/scoring":
            profile = _get_state_repository().get_scoring_profile(user_id)
            return _response(200, {"profile": profile.model_dump(mode="json") if profile else None})
        if route_key == "PUT /profile/scoring":
            request = ScoringProfileInput.model_validate_json(event.get("body") or "{}")
            profile = _get_state_repository().save_scoring_profile(user_id, request)
            return _response(200, profile.model_dump(mode="json"))
        if route_key == "GET /settings/discovery":
            settings = _get_state_repository().get_discovery_settings()
            return _response(200, settings.model_dump(mode="json"))
        if route_key == "PUT /settings/discovery":
            request = DiscoverySettingsInput.model_validate_json(event.get("body") or "{}")
            settings = _get_state_repository().save_discovery_settings(request)
            return _response(200, settings.model_dump(mode="json"))
    except (ValidationError, ValueError) as exc:
        return _response(400, {"detail": str(exc)[:500]})
    except Exception:
        log.exception("dashboard request failed")
        return _response(500, {"detail": "internal server error"})

    return _response(404, {"detail": "route not found"})


def _parse_query(parameters: dict[str, str] | None) -> DashboardJobQuery:
    values = dict(parameters or {})
    if "eligibility" in values and "eligibility_status" not in values:
        values["eligibility_status"] = values.pop("eligibility")
    return DashboardJobQuery.model_validate(values)


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
