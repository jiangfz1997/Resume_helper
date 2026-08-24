from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Key

from job_discovery.dashboard.interfaces import DashboardUserStateRepository
from job_discovery.dashboard.models import (
    DashboardJobUserState,
    DashboardJobUserStatus,
    DashboardRunUserState,
    DashboardUserStateSnapshot,
    DiscoveryRunReport,
)
from job_discovery.domain.models import CoarseScore
from job_discovery.domain.normalize import normalize_company
from job_discovery.domain.settings import DiscoverySettings, DiscoverySettingsInput, ScoringProfileInput, UserScoringProfile
from job_discovery.repositories.dynamodb import _paginated

_BLOCKED_COMPANIES_KEY = "PREFS#BLOCKED_COMPANIES"


class DynamoDBDashboardUserStateRepository(DashboardUserStateRepository):
    def __init__(self, table_name: str, resource: Any = None) -> None:
        dynamodb = resource or boto3.resource("dynamodb")
        self._table = dynamodb.Table(table_name)

    def get_snapshot(self, user_id: str) -> DashboardUserStateSnapshot:
        items = _paginated(
            self._table.query,
            KeyConditionExpression=Key("user_id").eq(user_id),
            ConsistentRead=True,
        )
        jobs: list[DashboardJobUserState] = []
        runs: list[DashboardRunUserState] = []
        for item in items:
            entity_key = str(item["entity_key"])
            if entity_key.startswith("JOB#"):
                jobs.append(_to_job_state(item))
            elif entity_key.startswith("RUN#"):
                runs.append(_to_run_state(item))
        return DashboardUserStateSnapshot(jobs=jobs, runs=runs)

    def mark_job_viewed(self, user_id: str, job_id: UUID) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"JOB#{job_id}"},
            UpdateExpression=(
                "SET entity_type = :type, job_id = :job_id, "
                "first_viewed_at = if_not_exists(first_viewed_at, :now), "
                "last_viewed_at = :now, #status = if_not_exists(#status, :new), updated_at = :now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":type": "job", ":job_id": str(job_id), ":now": now, ":new": "new"},
        )

    def set_job_status(self, user_id: str, job_id: UUID, status: DashboardJobUserStatus) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"JOB#{job_id}"},
            UpdateExpression=(
                "SET entity_type = :type, job_id = :job_id, #status = :status, "
                "first_viewed_at = if_not_exists(first_viewed_at, :now), "
                "last_viewed_at = :now, updated_at = :now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":type": "job",
                ":job_id": str(job_id),
                ":status": status.value,
                ":now": now,
            },
        )

    def mark_run_viewed(self, user_id: str, run_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.put_item(
            Item={
                "user_id": user_id,
                "entity_key": f"RUN#{run_id}",
                "entity_type": "run",
                "run_id": run_id,
                "viewed_at": now,
                "updated_at": now,
            }
        )

    def list_blocked_companies(self, user_id: str) -> list[str]:
        item = self._table.get_item(
            Key={"user_id": user_id, "entity_key": _BLOCKED_COMPANIES_KEY}, ConsistentRead=True
        ).get("Item")
        return sorted(item.get("companies", [])) if item else []

    def block_company(self, user_id: str, company: str) -> list[str]:
        return self._mutate_blocklist(user_id, company, "ADD companies :company")

    def unblock_company(self, user_id: str, company: str) -> list[str]:
        return self._mutate_blocklist(user_id, company, "DELETE companies :company")

    def _mutate_blocklist(self, user_id: str, company: str, clause: str) -> list[str]:
        """ADD/DELETE on a DynamoDB string set, not a read-modify-write of a
        list: two tabs blocking different companies at the same time would
        otherwise silently drop one of them."""
        item = self._table.update_item(
            Key={"user_id": user_id, "entity_key": _BLOCKED_COMPANIES_KEY},
            UpdateExpression=f"SET entity_type = :type, updated_at = :now {clause}",
            ExpressionAttributeValues={
                ":type": "blocked_companies",
                ":now": datetime.now(timezone.utc).isoformat(),
                ":company": {normalize_company(company)},
            },
            ReturnValues="ALL_NEW",
        )["Attributes"]
        return sorted(item.get("companies", []))

    def get_scoring_profile(self, user_id: str) -> UserScoringProfile | None:
        item = self._table.get_item(
            Key={"user_id": user_id, "entity_key": "PROFILE#SCORING"}, ConsistentRead=True
        ).get("Item")
        return _to_profile(item) if item else None

    def save_scoring_profile(self, user_id: str, profile: ScoringProfileInput) -> UserScoringProfile:
        now = datetime.now(timezone.utc).isoformat()
        values = {
            ":type": "profile",
            ":skills": profile.skills,
            ":titles": profile.target_titles,
            ":years": profile.min_years_experience,
            ":location": profile.location_preference,
            ":new_grad": profile.prefers_new_grad,
            ":active": profile.active,
            ":now": now,
            ":zero": 0,
            ":one": 1,
        }
        item = self._table.update_item(
            Key={"user_id": user_id, "entity_key": "PROFILE#SCORING"},
            UpdateExpression=(
                "SET entity_type = :type, skills = :skills, target_titles = :titles, "
                "min_years_experience = :years, location_preference = :location, "
                "prefers_new_grad = :new_grad, "
                "active = :active, updated_at = :now, profile_version = if_not_exists(profile_version, :zero) + :one"
            ),
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )["Attributes"]
        return _to_profile(item)

    def list_scoring_profiles(self) -> list[UserScoringProfile]:
        items = _paginated(self._table.scan, ConsistentRead=True)
        return [_to_profile(item) for item in items if item.get("entity_key") == "PROFILE#SCORING"]

    def get_discovery_settings(self) -> DiscoverySettings:
        item = self._table.get_item(
            Key={"user_id": "SYSTEM", "entity_key": "SETTINGS#DISCOVERY"}, ConsistentRead=True
        ).get("Item")
        return _to_discovery_settings(item) if item else DiscoverySettings()

    def save_discovery_settings(self, settings: DiscoverySettingsInput) -> DiscoverySettings:
        now = datetime.now(timezone.utc).isoformat()
        item = self._table.update_item(
            Key={"user_id": "SYSTEM", "entity_key": "SETTINGS#DISCOVERY"},
            UpdateExpression=(
                "SET entity_type = :type, search_terms = :terms, jobspy_location = :location, "
                "hours_old = :hours, jobspy_max_results = :jobspy_max, workday_max_results = :workday_max, "
                "sites = :sites, accepted_locations = :accepted, include_title_keywords = :include, "
                "exclude_title_keywords = :exclude, review_title_keywords = :review, "
                "min_description_chars = :min_chars, max_required_years = :max_years, "
                "updated_at = :now, "
                "config_version = if_not_exists(config_version, :zero) + :one"
            ),
            ExpressionAttributeValues={
                ":type": "discovery_settings", ":terms": settings.search_terms,
                ":location": settings.jobspy_location, ":hours": settings.hours_old,
                ":jobspy_max": settings.jobspy_max_results, ":workday_max": settings.workday_max_results,
                ":sites": settings.sites, ":accepted": settings.accepted_locations,
                ":include": settings.include_title_keywords, ":exclude": settings.exclude_title_keywords,
                ":review": settings.review_title_keywords, ":min_chars": settings.min_description_chars,
                ":max_years": settings.max_required_years,
                ":now": now, ":zero": 0, ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )["Attributes"]
        return _to_discovery_settings(item)

    def record_user_score(
        self, user_id: str, job_id: UUID, score: CoarseScore, score_version: str, profile_version: int
    ) -> None:
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"JOB#{job_id}"},
            UpdateExpression=(
                "SET entity_type = :type, job_id = :job_id, #status = if_not_exists(#status, :new), "
                "coarse_score = :score, coarse_score_reasoning = :reasoning, score_model = :model, "
                "score_version = :version, profile_version = :profile_version, scored_at = :scored_at, "
                "scoring_status = :scored, scoring_profile_version = :profile_version, "
                "updated_at = :scored_at REMOVE score_error"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":type": "job", ":job_id": str(job_id), ":new": "new", ":score": score.score,
                ":reasoning": score.reasoning, ":model": score.model, ":version": score_version,
                ":profile_version": profile_version, ":scored_at": score.scored_at.isoformat(), ":scored": "scored",
            },
        )

    def mark_user_score_queued(self, user_id: str, job_id: UUID, profile_version: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"JOB#{job_id}"},
            UpdateExpression=(
                "SET entity_type = :type, job_id = :job_id, #status = if_not_exists(#status, :new), "
                "scoring_status = :queued, scoring_profile_version = :profile_version, "
                "updated_at = :now REMOVE score_error"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":type": "job", ":job_id": str(job_id), ":new": "new", ":queued": "queued",
                ":profile_version": profile_version, ":now": now,
            },
        )

    def record_user_score_failure(
        self, user_id: str, job_id: UUID, score_version: str, profile_version: int, error: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"JOB#{job_id}"},
            UpdateExpression=(
                "SET entity_type = :type, job_id = :job_id, #status = if_not_exists(#status, :new), "
                "scoring_status = :failed, score_error = :error, score_version = :version, "
                "scoring_profile_version = :profile_version, updated_at = :now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":type": "job", ":job_id": str(job_id), ":new": "new", ":failed": "failed",
                ":error": error[:500], ":version": score_version, ":profile_version": profile_version, ":now": now,
            },
        )

    def record_discovery_run(self, report: DiscoveryRunReport) -> None:
        self._table.put_item(Item={
            "user_id": "SYSTEM",
            "entity_key": f"DISCOVERY_RUN#{report.run_id}#{report.runner}",
            "entity_type": "discovery_run",
            **report.model_dump(mode="json"),
        })

    def list_discovery_runs(self) -> list[DiscoveryRunReport]:
        items = _paginated(
            self._table.query,
            KeyConditionExpression=Key("user_id").eq("SYSTEM") & Key("entity_key").begins_with("DISCOVERY_RUN#"),
            ConsistentRead=True,
        )
        return [DiscoveryRunReport.model_validate(item) for item in items]


def _to_job_state(item: dict[str, Any]) -> DashboardJobUserState:
    return DashboardJobUserState(
        job_id=UUID(item["job_id"]),
        status=DashboardJobUserStatus(item.get("status", "new")),
        first_viewed_at=datetime.fromisoformat(item["first_viewed_at"]) if item.get("first_viewed_at") else None,
        last_viewed_at=datetime.fromisoformat(item["last_viewed_at"]) if item.get("last_viewed_at") else None,
        updated_at=datetime.fromisoformat(item["updated_at"]),
        coarse_score=int(item["coarse_score"]) if item.get("coarse_score") is not None else None,
        coarse_score_reasoning=item.get("coarse_score_reasoning"),
        score_model=item.get("score_model"),
        score_version=item.get("score_version"),
        profile_version=int(item["profile_version"]) if item.get("profile_version") is not None else None,
        scored_at=datetime.fromisoformat(item["scored_at"]) if item.get("scored_at") else None,
        scoring_status=item.get("scoring_status"),
        scoring_profile_version=(
            int(item["scoring_profile_version"]) if item.get("scoring_profile_version") is not None else None
        ),
        score_error=item.get("score_error"),
    )


def _to_run_state(item: dict[str, Any]) -> DashboardRunUserState:
    return DashboardRunUserState(
        run_id=item["run_id"],
        viewed_at=datetime.fromisoformat(item["viewed_at"]),
    )


def _to_profile(item: dict[str, Any]) -> UserScoringProfile:
    return UserScoringProfile(
        user_id=item["user_id"], skills=list(item.get("skills", [])),
        target_titles=list(item.get("target_titles", [])),
        min_years_experience=int(item["min_years_experience"]) if item.get("min_years_experience") is not None else None,
        location_preference=item.get("location_preference"),
        prefers_new_grad=bool(item.get("prefers_new_grad", False)), active=bool(item.get("active", True)),
        profile_version=int(item.get("profile_version", 1)), updated_at=datetime.fromisoformat(item["updated_at"]),
    )


def _to_discovery_settings(item: dict[str, Any]) -> DiscoverySettings:
    payload = {field: item[field] for field in DiscoverySettingsInput.model_fields if field in item}
    # Older settings rows stored null for "no limit". Scoring now has a
    # mandatory early-career ceiling, so normalize those rows to the current
    # default without requiring a destructive migration just to read them.
    if payload.get("max_required_years") is None:
        payload.pop("max_required_years", None)
    return DiscoverySettings(
        **payload, config_version=int(item.get("config_version", 1)),
        updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
    )
