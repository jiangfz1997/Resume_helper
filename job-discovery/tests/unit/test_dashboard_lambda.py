from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

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
        "queryStringParameters": {"limit": "500"},
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
