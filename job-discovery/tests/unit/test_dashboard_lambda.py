from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID, uuid4

from job_discovery.dashboard.models import DashboardJobUserStatus, DashboardUserStateSnapshot
from job_discovery.domain.models import EligibilityStatus
from job_discovery.domain.settings import ScoringProfileInput, UserScoringProfile

ROOT = Path(__file__).parents[2]


def _load_lambda() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dashboard_lambda", ROOT / "lambda_dashboard" / "lambda_function.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_list_does_not_require_claims(monkeypatch) -> None:
    class EmptyReader:
        def list_records(self) -> list:
            return []

        def list_all_listings(self) -> list:
            return []

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._reader = EmptyReader()

    response = module.lambda_handler({"routeKey": "GET /jobs"}, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Cache-Control"].startswith("public")


def test_missing_claims_cannot_access_private_route(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()

    response = module.lambda_handler({"routeKey": "GET /user-state"}, None)

    assert response["statusCode"] == 401


def test_missing_claims_cannot_write_job_state(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()

    response = module.lambda_handler({"routeKey": "PUT /jobs/{job_id}/state"}, None)

    assert response["statusCode"] == 401


def test_invalid_query_returns_400(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    event = {
        "routeKey": "GET /jobs",
        "queryStringParameters": {"limit": "501"},
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert "detail" in json.loads(response["body"])


def test_authenticated_list_returns_page(monkeypatch) -> None:
    class EmptyReader:
        def list_records(self) -> list:
            return []

        def list_all_listings(self) -> list:
            return []

    class FakeStateRepository:
        def list_blocked_companies(self, user_id: str) -> list[str]:
            return []

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._reader = EmptyReader()
    module._state_repository = FakeStateRepository()
    event = {
        "routeKey": "GET /jobs",
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body == {"schema_version": "job-dashboard.v1", "items": [], "total": 0}
    # Personal filtering rules out the shared CloudFront cache entry.
    assert response["headers"]["Cache-Control"] == "no-store"


def test_authenticated_user_can_update_job_state(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeStateRepository:
        def set_job_status(self, user_id: str, job_id: UUID, status: DashboardJobUserStatus) -> None:
            calls.append((user_id, str(job_id), status.value))

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._state_repository = FakeStateRepository()
    job_id = "6e02c6de-1547-4efd-b54a-b531058d9d87"
    event = {
        "routeKey": "PUT /jobs/{job_id}/state",
        "pathParameters": {"job_id": job_id},
        "body": '{"status":"applied"}',
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert calls == [("user-1", job_id, "applied")]


def test_profile_update_is_scoped_to_authenticated_user(monkeypatch) -> None:
    calls: list[tuple[str, ScoringProfileInput]] = []

    class FakeStateRepository:
        def save_scoring_profile(self, user_id: str, profile: ScoringProfileInput) -> UserScoringProfile:
            calls.append((user_id, profile))
            return UserScoringProfile(
                user_id=user_id, **profile.model_dump(), profile_version=1, updated_at=datetime.now(timezone.utc)
            )

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._state_repository = FakeStateRepository()
    event = {
        "routeKey": "PUT /profile/scoring",
        "body": '{"skills":["Python"],"target_titles":["Backend Engineer"],"active":true}',
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "cognito-user-a"}}}},
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert calls[0][0] == "cognito-user-a"
    assert calls[0][1].skills == ["Python"]


def test_authenticated_user_can_queue_one_job_for_scoring(monkeypatch) -> None:
    invocations: list[dict] = []

    class FakeReader:
        def get_record(self, job_id: UUID) -> object:
            return object()

    class FakeLambdaClient:
        def invoke(self, **kwargs: object) -> None:
            invocations.append(kwargs)

    class FakeStateRepository:
        def get_scoring_profile(self, user_id: str) -> UserScoringProfile:
            return UserScoringProfile(
                user_id=user_id, skills=["Python"], active=True, profile_version=3,
                updated_at=datetime.now(timezone.utc),
            )

        def mark_user_score_queued(self, user_id: str, job_id: UUID, profile_version: int) -> None:
            assert (user_id, profile_version) == ("user-1", 3)

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("SCORING_FUNCTION_NAME", "job-discovery-score")
    module = _load_lambda()
    module._reader = FakeReader()
    module._state_repository = FakeStateRepository()
    module._lambda_client = FakeLambdaClient()
    job_id = "6e02c6de-1547-4efd-b54a-b531058d9d87"
    event = {
        "routeKey": "POST /jobs/{job_id}/score",
        "pathParameters": {"job_id": job_id},
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)
    payload = json.loads(invocations[0]["Payload"].decode("utf-8"))

    assert response["statusCode"] == 202
    assert payload == {"user_ids": ["user-1"], "job_ids": [job_id], "limit": 1}


def test_manual_run_scoring_caps_at_unscored_eligible_jobs(monkeypatch) -> None:
    invocations: list[dict] = []
    queued: list[UUID] = []
    run_id = "lambda-2026-08-09T12:00Z"
    job_ids = [uuid4() for _ in range(4)]
    records = [
        SimpleNamespace(
            job_id=job_id,
            first_discovered_run_id=run_id,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            created_at=datetime(2026, 8, 9, 12, index, tzinfo=timezone.utc),
        )
        for index, job_id in enumerate(job_ids)
    ]

    class FakeReader:
        def list_records(self) -> list:
            return records

    class FakeLambdaClient:
        def invoke(self, **kwargs: object) -> None:
            invocations.append(kwargs)

    class FakeStateRepository:
        def get_scoring_profile(self, user_id: str) -> UserScoringProfile:
            return UserScoringProfile(
                user_id=user_id, skills=["Python"], active=True, profile_version=3,
                updated_at=datetime.now(timezone.utc),
            )

        def get_snapshot(self, user_id: str) -> DashboardUserStateSnapshot:
            assert user_id == "user-1"
            return DashboardUserStateSnapshot(jobs=[
                {
                    "job_id": job_ids[0], "updated_at": datetime.now(timezone.utc),
                    "coarse_score": 8, "profile_version": 3,
                },
                {
                    "job_id": job_ids[1], "updated_at": datetime.now(timezone.utc),
                    "scoring_status": "queued", "scoring_profile_version": 3,
                },
            ])

        def mark_user_score_queued(self, user_id: str, job_id: UUID, profile_version: int) -> None:
            assert (user_id, profile_version) == ("user-1", 3)
            queued.append(job_id)

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("SCORING_FUNCTION_NAME", "job-discovery-score")
    module = _load_lambda()
    module._reader = FakeReader()
    module._state_repository = FakeStateRepository()
    module._lambda_client = FakeLambdaClient()
    event = {
        "routeKey": "POST /actions/scoring",
        "body": json.dumps({"run_id": run_id, "limit": 100}),
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)
    body = json.loads(response["body"])
    payload = json.loads(invocations[0]["Payload"].decode("utf-8"))

    assert response["statusCode"] == 202
    assert body == {"ok": True, "run_id": run_id, "eligible": 4, "remaining": 2, "queued": 2}
    assert set(queued) == set(job_ids[2:])
    assert set(payload["job_ids"]) == {str(job_id) for job_id in job_ids[2:]}
    assert payload["limit"] == 2


def test_manual_crawler_invokes_selected_functions_with_one_run_id(monkeypatch) -> None:
    invocations: list[dict] = []

    class FakeLambdaClient:
        def invoke(self, **kwargs: object) -> None:
            invocations.append(kwargs)

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("WORKDAY_FUNCTION_NAME", "workday-function")
    monkeypatch.setenv("JOBSPY_FUNCTION_NAME", "jobspy-function")
    module = _load_lambda()
    module._lambda_client = FakeLambdaClient()
    event = {
        "routeKey": "POST /actions/crawler",
        "body": '{"crawler":"both"}',
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)
    body = json.loads(response["body"])
    payloads = [json.loads(call["Payload"].decode("utf-8")) for call in invocations]

    assert response["statusCode"] == 202
    assert [call["FunctionName"] for call in invocations] == ["workday-function", "jobspy-function"]
    assert payloads == [{"run_id": body["run_id"]}, {"run_id": body["run_id"]}]


def test_missing_claims_cannot_block_a_company(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()

    response = module.lambda_handler({"routeKey": "POST /blocked-companies"}, None)

    assert response["statusCode"] == 401


def test_blocking_a_company_is_scoped_to_the_authenticated_user(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeStateRepository:
        def block_company(self, user_id: str, company: str) -> list[str]:
            calls.append(("block", user_id, company))
            return ["jobright.ai"]

        def unblock_company(self, user_id: str, company: str) -> list[str]:
            calls.append(("unblock", user_id, company))
            return []

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._state_repository = FakeStateRepository()
    claims = {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}}

    blocked = module.lambda_handler({
        "routeKey": "POST /blocked-companies",
        "body": '{"company":"Jobright.ai"}',
        "requestContext": claims,
    }, None)
    restored = module.lambda_handler({
        "routeKey": "DELETE /blocked-companies/{company}",
        "pathParameters": {"company": "jobright.ai"},
        "requestContext": claims,
    }, None)

    assert json.loads(blocked["body"]) == {"companies": ["jobright.ai"]}
    assert json.loads(restored["body"]) == {"companies": []}
    assert calls == [("block", "user-1", "Jobright.ai"), ("unblock", "user-1", "jobright.ai")]


def test_blocking_an_empty_company_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    event = {
        "routeKey": "POST /blocked-companies",
        "body": '{"company":""}',
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 400
