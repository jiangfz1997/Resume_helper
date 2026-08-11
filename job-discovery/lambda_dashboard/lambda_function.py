from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any
from urllib.parse import unquote
from uuid import UUID, uuid4

import boto3
from pydantic import ValidationError

from job_discovery.dashboard.interfaces import DashboardJobReader, DashboardUserStateRepository
from job_discovery.dashboard.models import (
    BlockCompanyRequest,
    DashboardJobQuery,
    DashboardJobUserStatus,
    ManualCrawlerRequest,
    ManualScoringRequest,
    UpdateJobStateRequest,
)
from job_discovery.dashboard.service import (
    get_dashboard_bootstrap,
    get_dashboard_job,
    get_scoring_queue,
    list_dashboard_jobs,
    list_dashboard_runs,
)
from job_discovery.domain.models import EligibilityStatus
from job_discovery.domain.settings import DiscoverySettingsInput, ScoringProfileInput
from job_discovery.repositories.dashboard_cache import CachingDashboardJobReader
from job_discovery.repositories.dynamodb_dashboard import DynamoDBDashboardJobReader
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

_reader: DashboardJobReader | None = None
_state_repository: DashboardUserStateRepository | None = None
_lambda_client: Any = None

PUBLIC_ROUTES = {
    "GET /jobs",
    "GET /jobs/{job_id}",
    "GET /runs",
}


def _get_reader() -> DashboardJobReader:
    global _reader
    if _reader is None:
        base_reader = DynamoDBDashboardJobReader(
            records_table=os.environ["RECORDS_TABLE"],
            listings_table=os.environ["LISTINGS_TABLE"],
        )
        ttl_seconds = float(os.environ.get("DASHBOARD_CACHE_TTL_SECONDS", "30"))
        _reader = CachingDashboardJobReader(base_reader, ttl_seconds=ttl_seconds)
    return _reader


def _get_state_repository() -> DashboardUserStateRepository:
    global _state_repository
    if _state_repository is None:
        _state_repository = DynamoDBDashboardUserStateRepository(os.environ["USER_DATA_TABLE"])
    return _state_repository


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    route_key = event.get("routeKey", "")
    claims = _claims(event)
    if (
        os.environ.get("REQUIRE_AUTH", "true").casefold() == "true"
        and route_key not in PUBLIC_ROUTES
        and not claims
    ):
        return _response(401, {"detail": "authentication required"})
    user_id = str(claims.get("sub", ""))

    try:
        if route_key == "GET /bootstrap":
            query = _parse_query(event.get("queryStringParameters"))
            bootstrap = get_dashboard_bootstrap(_get_reader(), _get_state_repository(), user_id, query)
            return _response(200, bootstrap.model_dump(mode="json"))
        if route_key == "GET /jobs":
            query = _parse_query(event.get("queryStringParameters"))
            # A signed-in caller gets their blocklist applied, which makes the
            # response personal and therefore uncacheable by CloudFront.
            blocked = _get_state_repository().list_blocked_companies(user_id) if user_id else []
            return _response(
                200,
                list_dashboard_jobs(_get_reader(), query, blocked).model_dump(mode="json"),
                cache_control="no-store" if user_id else "public, max-age=60, stale-while-revalidate=300",
            )
        if route_key == "GET /jobs/{job_id}":
            job_id = UUID((event.get("pathParameters") or {}).get("job_id", ""))
            job = get_dashboard_job(_get_reader(), job_id)
            if job is None:
                return _response(404, {"detail": "job not found"})
            return _response(
                200,
                job.model_dump(mode="json"),
                cache_control="public, max-age=300, stale-while-revalidate=600",
            )
        if route_key == "GET /runs":
            reports = _get_state_repository().list_discovery_runs()
            return _response(
                200,
                list_dashboard_runs(_get_reader(), reports).model_dump(mode="json"),
                cache_control="public, max-age=60, stale-while-revalidate=300",
            )
        if route_key == "GET /scoring/queue":
            state = _get_state_repository().get_snapshot(user_id)
            profile = _get_state_repository().get_scoring_profile(user_id)
            queue = get_scoring_queue(
                _get_reader(),
                state.jobs,
                profile.profile_version if profile else None,
                _get_state_repository().list_blocked_companies(user_id),
            )
            return _response(200, queue.model_dump(mode="json"))
        if route_key == "POST /jobs/{job_id}/score":
            job_id = UUID((event.get("pathParameters") or {}).get("job_id", ""))
            if _get_reader().get_record(job_id) is None:
                return _response(404, {"detail": "job not found"})
            profile = _get_state_repository().get_scoring_profile(user_id)
            if profile is None or not profile.active:
                return _response(409, {"detail": "an active scoring profile is required"})
            _get_state_repository().mark_user_score_queued(user_id, job_id, profile.profile_version)
            try:
                _invoke_scoring(user_id, job_id)
            except Exception as exc:
                _get_state_repository().record_user_score_failure(
                    user_id, job_id, "manual-invoke", profile.profile_version, str(exc)
                )
                raise
            return _response(202, {"ok": True, "status": "queued"})
        if route_key == "POST /actions/scoring":
            request = ManualScoringRequest.model_validate_json(event.get("body") or "{}")
            profile = _get_state_repository().get_scoring_profile(user_id)
            if profile is None or not profile.active:
                return _response(409, {"detail": "an active scoring profile is required"})
            records = [
                record for record in _get_reader().list_records()
                if record.first_discovered_run_id == request.run_id
            ]
            if not records:
                return _response(404, {"detail": "run not found or contains no newly discovered jobs"})
            eligible = [record for record in records if record.eligibility_status is EligibilityStatus.ELIGIBLE]
            state_by_job = {
                state.job_id: state for state in _get_state_repository().get_snapshot(user_id).jobs
            }
            candidates = []
            for record in sorted(eligible, key=lambda item: item.created_at, reverse=True):
                state = state_by_job.get(record.job_id)
                if state and state.status in {DashboardJobUserStatus.APPLIED, DashboardJobUserStatus.REJECTED}:
                    continue
                if state and state.coarse_score is not None and state.profile_version == profile.profile_version:
                    continue
                if state and state.scoring_status == "queued" and state.scoring_profile_version == profile.profile_version:
                    continue
                candidates.append(record)
            selected = candidates[:request.limit]
            for record in selected:
                _get_state_repository().mark_user_score_queued(user_id, record.job_id, profile.profile_version)
            if selected:
                try:
                    _invoke_scoring_jobs(user_id, [record.job_id for record in selected])
                except Exception as exc:
                    for record in selected:
                        _get_state_repository().record_user_score_failure(
                            user_id, record.job_id, "manual-invoke", profile.profile_version, str(exc)
                        )
                    raise
            return _response(202, {
                "ok": True,
                "run_id": request.run_id,
                "eligible": len(eligible),
                "remaining": len(candidates),
                "queued": len(selected),
            })
        if route_key == "POST /actions/crawler":
            request = ManualCrawlerRequest.model_validate_json(event.get("body") or "{}")
            run_id = f"manual-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}-{uuid4().hex[:8]}"
            if request.crawler == "all":
                crawlers = ["workday", "jobspy", "simplify"]
            elif request.crawler == "both":
                crawlers = ["workday", "jobspy"]
            else:
                crawlers = [request.crawler]
            _invoke_crawlers(crawlers, run_id)
            return _response(202, {"ok": True, "run_id": run_id, "crawlers": crawlers})
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
        if route_key == "GET /blocked-companies":
            companies = _get_state_repository().list_blocked_companies(user_id)
            return _response(200, {"companies": companies})
        if route_key == "POST /blocked-companies":
            request = BlockCompanyRequest.model_validate_json(event.get("body") or "{}")
            companies = _get_state_repository().block_company(user_id, request.company)
            return _response(200, {"companies": companies})
        if route_key == "DELETE /blocked-companies/{company}":
            company = unquote((event.get("pathParameters") or {}).get("company", "")).strip()
            if not company:
                raise ValueError("company is required")
            companies = _get_state_repository().unblock_company(user_id, company)
            return _response(200, {"companies": companies})
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


def _invoke_scoring(user_id: str, job_id: UUID) -> None:
    _invoke_scoring_jobs(user_id, [job_id])


def _invoke_scoring_jobs(user_id: str, job_ids: list[UUID]) -> None:
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    _lambda_client.invoke(
        FunctionName=os.environ["SCORING_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({
            "user_ids": [user_id],
            "job_ids": [str(job_id) for job_id in job_ids],
            "limit": len(job_ids),
        }).encode("utf-8"),
    )


def _invoke_crawlers(crawlers: list[str], run_id: str) -> None:
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    function_names = {
        "workday": os.environ["WORKDAY_FUNCTION_NAME"],
        "jobspy": os.environ["JOBSPY_FUNCTION_NAME"],
        "simplify": os.environ["SIMPLIFY_FUNCTION_NAME"],
        "simplify_canada": os.environ["SIMPLIFY_FUNCTION_NAME"],
        "simplify_github": os.environ["SIMPLIFY_FUNCTION_NAME"],
    }
    for crawler in crawlers:
        payload: dict[str, Any] = {"run_id": run_id}
        if crawler == "simplify_canada":
            payload["feeds"] = ["canada"]
        elif crawler == "simplify_github":
            payload["feeds"] = ["github"]
        _lambda_client.invoke(
            FunctionName=function_names[crawler],
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )


def _response(
    status_code: int,
    body: dict[str, Any],
    *,
    cache_control: str = "no-store",
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": cache_control,
    }
    allowed_origin = os.environ.get("ALLOWED_ORIGIN")
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":")),
    }
