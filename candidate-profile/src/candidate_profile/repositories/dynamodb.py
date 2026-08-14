"""Single-table DynamoDB repository: user_id (HASH) / entity_key (RANGE).

Same shape as job-discovery's DynamoDBDashboardUserStateRepository -- one
item per profile ("PROFILE"), one item per application ("APPLICATION#<id>").
Deliberately a separate table from job-discovery's own user-data table: this
service owns candidate-side data (resume profile, application history), not
the job-discovery crawl/score domain, so the two must be able to evolve and
redeploy independently.

Single-item reads use ConsistentRead=True; the application list is
eventually consistent and applies status and text filters in Python, which
is fine at personal-tracker volume (tens to low hundreds of applications).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from candidate_profile.domain.models import (
    ApplicationListQuery,
    ApplicationSourceType,
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

# Everything the list view needs. raw_html is deliberately absent: it is a
# page snapshot kept only for diagnosing a bad extraction, is never rendered,
# and runs to MAX_RAW_HTML_CHARS per item -- projecting it would let a single
# item dominate the response for no reader. get_application still returns it.
_LIST_ATTRIBUTES = (
    "user_id",
    "application_id",
    "source_type",
    "job_id",
    "source_url",
    "apply_url",
    "company",
    "title",
    "location",
    "jd_text",
    "status",
    "status_history",
    "extraction_status",
    "extraction_error",
    "notes",
    "applied_at",
    "created_at",
    "updated_at",
)
# Every attribute is aliased, not just the ones that happen to collide today
# ("status", "location", "source"), so extending the tuple above can never
# silently trip over DynamoDB's reserved-word list.
_LIST_PROJECTION_NAMES = {f"#{name}": name for name in _LIST_ATTRIBUTES}
_LIST_PROJECTION = ", ".join(_LIST_PROJECTION_NAMES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches_application(application: JobApplication, query: ApplicationListQuery) -> bool:
    if query.status is not None and application.status is not query.status:
        return False
    if query.job is not None and query.job.casefold() not in application.title.casefold():
        return False
    if query.company is not None and query.company.casefold() not in application.company.casefold():
        return False
    if query.q is not None:
        search = query.q.casefold()
        if search not in application.title.casefold() and search not in application.company.casefold():
            return False
    return True


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

    def prewarm(self) -> None:
        """Resolve credentials and open the TLS connection to DynamoDB.

        Callers run this during Lambda's INIT phase so the first real request
        does not pay for the handshake. Failures are swallowed on purpose: a
        throttled or unavailable warm-up must never take the function down,
        the request path will simply pay the cost it would have paid anyway.
        """
        try:
            self._table.get_item(Key={"user_id": "__prewarm__", "entity_key": "PROFILE"})
        except Exception:  # noqa: BLE001 - best effort, never fatal
            pass

    # ── profile ──────────────────────────────────────────────

    def get_profile(self, user_id: str) -> CandidateProfile | None:
        item = self._table.get_item(
            Key={"user_id": user_id, "entity_key": "PROFILE"}, ConsistentRead=True
        ).get("Item")
        return _to_profile(item) if item else None

    def save_profile(self, user_id: str, data: CandidateProfileInput) -> CandidateProfile:
        now = _now()
        payload = data.model_dump(mode="json")
        names = {f"#{field}": field for field in payload}
        values: dict[str, Any] = {
            **{f":{field}": value for field, value in payload.items()},
            ":entity_type": "profile",
            ":updated_at": now,
            ":zero": 0,
            ":one": 1,
        }
        assignments = [f"#{field} = :{field}" for field in payload]
        assignments.extend(
            [
                "entity_type = :entity_type",
                "updated_at = :updated_at",
                "profile_version = if_not_exists(profile_version, :zero) + :one",
            ]
        )
        item = self._table.update_item(
            Key={"user_id": user_id, "entity_key": "PROFILE"},
            UpdateExpression="SET " + ", ".join(assignments),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )["Attributes"]
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

    def list_applications(self, user_id: str, query: ApplicationListQuery | None = None) -> list[JobApplication]:
        items = _paginated(
            self._table.query,
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("entity_key").begins_with("APPLICATION#"),
            ProjectionExpression=_LIST_PROJECTION,
            ExpressionAttributeNames=_LIST_PROJECTION_NAMES,
        )
        applications = [_to_application(item) for item in items]
        if query is not None:
            applications = [application for application in applications if _matches_application(application, query)]
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


def _to_profile(item: dict[str, Any]) -> CandidateProfile:
    payload = {field: item[field] for field in CandidateProfileInput.model_fields if field in item}
    return CandidateProfile(
        user_id=item["user_id"],
        profile_version=int(item.get("profile_version", 1)),
        updated_at=datetime.fromisoformat(item["updated_at"]),
        **payload,
    )


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
