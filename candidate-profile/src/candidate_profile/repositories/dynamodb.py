"""Single-table DynamoDB repository: user_id (HASH) / entity_key (RANGE).

Same shape as job-discovery's DynamoDBDashboardUserStateRepository -- one
item per profile ("PROFILE"), one item per application ("APPLICATION#<id>").
Deliberately a separate table from job-discovery's own user-data table: this
service owns candidate-side data (resume profile, application history), not
the job-discovery crawl/score domain, so the two must be able to evolve and
redeploy independently.

All reads are primary-key reads with ConsistentRead=True; application
listing/stats scan this user's partition and filter in Python, which is
fine at personal-tracker volume (tens to low hundreds of applications).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from candidate_profile.domain.models import (
    ApplicationSourceType,
    ApplicationStats,
    ApplicationStatus,
    ApplicationStatusEvent,
    CandidateProfile,
    CandidateProfileInput,
    CreateApplicationFromJob,
    ExtractedJobInfo,
    ExtractionStatus,
    JobApplication,
    UpdateApplicationFields,
)

# DynamoDB items are capped at 400KB; leave generous headroom for the other
# attributes on an application item (jd_text, status history, ...).
MAX_RAW_HTML_CHARS = 150_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paginated(operation: Any, **kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    response = operation(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = operation(ExclusiveStartKey=response["LastEvaluatedKey"], **kwargs)
        items.extend(response.get("Items", []))
    return items


class DynamoDBCandidateProfileRepository:
    def __init__(self, table_name: str, resource: Any = None) -> None:
        dynamodb = resource or boto3.resource("dynamodb")
        self._table = dynamodb.Table(table_name)

    # ── profile ──────────────────────────────────────────────

    def get_profile(self, user_id: str) -> CandidateProfile | None:
        item = self._table.get_item(
            Key={"user_id": user_id, "entity_key": "PROFILE"}, ConsistentRead=True
        ).get("Item")
        return _to_profile(item) if item else None

    def save_profile(self, user_id: str, data: CandidateProfileInput) -> CandidateProfile:
        now = _now()
        item = {
            "user_id": user_id,
            "entity_key": "PROFILE",
            "entity_type": "profile",
            **data.model_dump(mode="json"),
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        return _to_profile(item)

    # ── applications ─────────────────────────────────────────

    def create_application_from_job(self, user_id: str, data: CreateApplicationFromJob) -> JobApplication:
        now = _now()
        application_id = uuid.uuid4().hex
        item = {
            "user_id": user_id,
            "entity_key": f"APPLICATION#{application_id}",
            "entity_type": "application",
            "application_id": application_id,
            "source_type": ApplicationSourceType.DASHBOARD.value,
            "job_id": data.job_id,
            "source_url": data.source_url,
            "apply_url": data.apply_url,
            "company": data.company,
            "title": data.title,
            "location": data.location,
            "jd_text": data.jd_text,
            "raw_html": None,
            "status": ApplicationStatus.APPLIED.value,
            "status_history": [{"status": ApplicationStatus.APPLIED.value, "note": None, "changed_at": now}],
            "extraction_status": ExtractionStatus.READY.value,
            "extraction_error": None,
            "notes": None,
            "applied_at": now,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        return _to_application(item)

    def create_application_pending(self, user_id: str, url: str) -> JobApplication:
        now = _now()
        application_id = uuid.uuid4().hex
        item = {
            "user_id": user_id,
            "entity_key": f"APPLICATION#{application_id}",
            "entity_type": "application",
            "application_id": application_id,
            "source_type": ApplicationSourceType.MANUAL.value,
            "job_id": None,
            "source_url": url,
            "apply_url": None,
            "company": "",
            "title": "",
            "location": None,
            "jd_text": "",
            "raw_html": None,
            "status": ApplicationStatus.APPLIED.value,
            "status_history": [{"status": ApplicationStatus.APPLIED.value, "note": None, "changed_at": now}],
            "extraction_status": ExtractionStatus.EXTRACTING.value,
            "extraction_error": None,
            "notes": None,
            "applied_at": now,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        return _to_application(item)

    def complete_application_extraction(
        self, user_id: str, application_id: str, extracted: ExtractedJobInfo, raw_html: str | None
    ) -> None:
        now = _now()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"},
            UpdateExpression=(
                "SET company = :company, title = :title, #loc = :location, jd_text = :jd_text, "
                "raw_html = :raw_html, extraction_status = :ready, updated_at = :now "
                "REMOVE extraction_error"
            ),
            ExpressionAttributeNames={"#loc": "location"},
            ExpressionAttributeValues={
                ":company": extracted.company or "Unknown company",
                ":title": extracted.title or "Unknown title",
                ":location": extracted.location,
                ":jd_text": extracted.jd_text,
                ":raw_html": raw_html[:MAX_RAW_HTML_CHARS] if raw_html else None,
                ":ready": ExtractionStatus.READY.value,
                ":now": now,
            },
        )

    def fail_application_extraction(self, user_id: str, application_id: str, error: str) -> None:
        now = _now()
        self._table.update_item(
            Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"},
            UpdateExpression="SET extraction_status = :failed, extraction_error = :error, updated_at = :now",
            ExpressionAttributeValues={
                ":failed": ExtractionStatus.FAILED.value,
                ":error": error[:500],
                ":now": now,
            },
        )

    def list_applications(self, user_id: str, status: ApplicationStatus | None = None) -> list[JobApplication]:
        items = _paginated(
            self._table.query,
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("entity_key").begins_with("APPLICATION#"),
            ConsistentRead=True,
        )
        applications = [_to_application(item) for item in items]
        if status is not None:
            applications = [application for application in applications if application.status is status]
        applications.sort(key=lambda application: application.applied_at, reverse=True)
        return applications

    def get_application(self, user_id: str, application_id: str) -> JobApplication | None:
        item = self._table.get_item(
            Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"}, ConsistentRead=True
        ).get("Item")
        return _to_application(item) if item else None

    def update_application_status(
        self, user_id: str, application_id: str, status: ApplicationStatus, note: str | None
    ) -> JobApplication | None:
        now = _now()
        event = {"status": status.value, "note": note, "changed_at": now}
        try:
            item = self._table.update_item(
                Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"},
                UpdateExpression=(
                    "SET #status = :status, updated_at = :now, "
                    "status_history = list_append(if_not_exists(status_history, :empty), :event)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": status.value,
                    ":now": now,
                    ":empty": [],
                    ":event": [event],
                },
                ConditionExpression="attribute_exists(entity_key)",
                ReturnValues="ALL_NEW",
            )["Attributes"]
        except self._table.meta.client.exceptions.ConditionalCheckFailedException:
            return None
        return _to_application(item)

    def update_application_fields(
        self, user_id: str, application_id: str, data: UpdateApplicationFields
    ) -> JobApplication | None:
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return self.get_application(user_id, application_id)
        now = _now()
        set_clauses = ["updated_at = :now"]
        values: dict[str, Any] = {":now": now}
        names: dict[str, str] = {}
        for field, value in updates.items():
            placeholder = f":{field}"
            name_placeholder = f"#{field}"
            set_clauses.append(f"{name_placeholder} = {placeholder}")
            values[placeholder] = value
            names[name_placeholder] = field
        try:
            item = self._table.update_item(
                Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"},
                UpdateExpression="SET " + ", ".join(set_clauses),
                ExpressionAttributeValues=values,
                ExpressionAttributeNames=names,
                ConditionExpression="attribute_exists(entity_key)",
                ReturnValues="ALL_NEW",
            )["Attributes"]
        except self._table.meta.client.exceptions.ConditionalCheckFailedException:
            return None
        return _to_application(item)

    def delete_application(self, user_id: str, application_id: str) -> None:
        self._table.delete_item(Key={"user_id": user_id, "entity_key": f"APPLICATION#{application_id}"})

    def get_application_stats(self, user_id: str) -> ApplicationStats:
        applications = self.list_applications(user_id)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        today = sum(1 for application in applications if application.applied_at >= today_start)
        this_week = sum(1 for application in applications if application.applied_at >= week_start)
        by_status: dict[str, int] = {}
        for application in applications:
            by_status[application.status.value] = by_status.get(application.status.value, 0) + 1
        return ApplicationStats(today=today, this_week=this_week, total=len(applications), by_status=by_status)


def _to_profile(item: dict[str, Any]) -> CandidateProfile:
    payload = {field: item[field] for field in CandidateProfileInput.model_fields if field in item}
    return CandidateProfile(user_id=item["user_id"], updated_at=datetime.fromisoformat(item["updated_at"]), **payload)


def _to_application(item: dict[str, Any]) -> JobApplication:
    return JobApplication(
        application_id=item["application_id"],
        user_id=item["user_id"],
        source_type=ApplicationSourceType(item["source_type"]),
        job_id=item.get("job_id"),
        source_url=item.get("source_url"),
        apply_url=item.get("apply_url"),
        company=item.get("company", ""),
        title=item.get("title", ""),
        location=item.get("location"),
        jd_text=item.get("jd_text", ""),
        raw_html=item.get("raw_html"),
        status=ApplicationStatus(item["status"]),
        status_history=[ApplicationStatusEvent.model_validate(event) for event in item.get("status_history", [])],
        extraction_status=ExtractionStatus(item.get("extraction_status", ExtractionStatus.READY.value)),
        extraction_error=item.get("extraction_error"),
        notes=item.get("notes"),
        applied_at=datetime.fromisoformat(item["applied_at"]),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
    )
