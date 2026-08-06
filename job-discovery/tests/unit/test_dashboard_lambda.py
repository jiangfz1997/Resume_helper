from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from uuid import UUID

from job_discovery.dashboard.models import DashboardJobUserStatus
from job_discovery.domain.settings import ScoringProfileInput, UserScoringProfile

ROOT = Path(__file__).parents[2]


def _load_lambda() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dashboard_lambda", ROOT / "lambda_dashboard" / "lambda_function.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_claims_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()

    response = module.lambda_handler({"routeKey": "GET /jobs"}, None)

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

    monkeypatch.setenv("REQUIRE_AUTH", "true")
    module = _load_lambda()
    module._reader = EmptyReader()
    event = {
        "routeKey": "GET /jobs",
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}},
    }

    response = module.lambda_handler(event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body == {"schema_version": "job-dashboard.v1", "items": [], "total": 0}


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
