"""Tier A probers: public ATS JSON endpoints. Standard library only."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from probes.base import Prober, classify_http, request_json
from probes.models import (
    GreenhouseTarget,
    LeverTarget,
    ProbeOutcome,
    ProbeResult,
    ProbeTarget,
    ProbeTier,
    WorkdayTarget,
)


def _first_title(items: list[Any], *keys: str) -> str | None:
    if not items:
        return None
    head = items[0]
    if not isinstance(head, dict):
        return None
    for key in keys:
        value = head.get(key)
        if isinstance(value, str) and value:
            return value[:120]
    return None


class WorkdayProber(Prober):
    """Workday CXS search endpoint: POST /wday/cxs/{tenant}/{site_id}/jobs."""

    kind: ClassVar[str] = "workday"

    def probe(self, target: ProbeTarget) -> ProbeResult:
        t = cast(WorkdayTarget, target)
        url = f"{t.base_url}/wday/cxs/{t.tenant}/{t.site_id}/jobs"
        payload: dict[str, Any] = {
            "appliedFacets": {},
            "limit": 20,
            "offset": 0,
            "searchText": t.search_text,
        }
        response = request_json(url, payload=payload)

        postings: list[Any] = []
        total: int | None = None
        if response.status == 200:
            try:
                body = response.json()
                postings = body.get("jobPostings", []) or []
                total = body.get("total")
            except Exception as exc:
                return ProbeResult(
                    key=t.key,
                    name=t.name,
                    kind=self.kind,
                    tier=ProbeTier.ATS,
                    outcome=ProbeOutcome.ERROR,
                    http_status=response.status,
                    elapsed_ms=response.elapsed_ms,
                    detail=f"200 but body is not the expected JSON: {exc}",
                )

        outcome, detail = classify_http(response, len(postings))
        if total is not None and detail is None:
            detail = f"total={total}"
        return ProbeResult(
            key=t.key,
            name=t.name,
            kind=self.kind,
            tier=ProbeTier.ATS,
            outcome=outcome,
            http_status=response.status or None,
            item_count=len(postings),
            elapsed_ms=response.elapsed_ms,
            sample_title=_first_title(postings, "title"),
            detail=detail,
        )


class GreenhouseProber(Prober):
    """Greenhouse job board API: GET /v1/boards/{token}/jobs."""

    kind: ClassVar[str] = "greenhouse"

    def probe(self, target: ProbeTarget) -> ProbeResult:
        t = cast(GreenhouseTarget, target)
        url = f"https://boards-api.greenhouse.io/v1/boards/{t.board_token}/jobs"
        response = request_json(url)

        jobs: list[Any] = []
        if response.status == 200:
            try:
                jobs = response.json().get("jobs", []) or []
            except Exception as exc:
                return ProbeResult(
                    key=t.key,
                    name=t.name,
                    kind=self.kind,
                    tier=ProbeTier.ATS,
                    outcome=ProbeOutcome.ERROR,
                    http_status=response.status,
                    elapsed_ms=response.elapsed_ms,
                    detail=f"200 but body is not the expected JSON: {exc}",
                )

        outcome, detail = classify_http(response, len(jobs))
        return ProbeResult(
            key=t.key,
            name=t.name,
            kind=self.kind,
            tier=ProbeTier.ATS,
            outcome=outcome,
            http_status=response.status or None,
            item_count=len(jobs),
            elapsed_ms=response.elapsed_ms,
            sample_title=_first_title(jobs, "title"),
            detail=detail,
        )


class LeverProber(Prober):
    """Lever postings API: GET /v0/postings/{company}?mode=json."""

    kind: ClassVar[str] = "lever"

    def probe(self, target: ProbeTarget) -> ProbeResult:
        t = cast(LeverTarget, target)
        url = f"https://api.lever.co/v0/postings/{t.company}?mode=json"
        response = request_json(url)

        postings: list[Any] = []
        if response.status == 200:
            try:
                body = response.json()
                postings = body if isinstance(body, list) else []
            except Exception as exc:
                return ProbeResult(
                    key=t.key,
                    name=t.name,
                    kind=self.kind,
                    tier=ProbeTier.ATS,
                    outcome=ProbeOutcome.ERROR,
                    http_status=response.status,
                    elapsed_ms=response.elapsed_ms,
                    detail=f"200 but body is not the expected JSON: {exc}",
                )

        outcome, detail = classify_http(response, len(postings))
        return ProbeResult(
            key=t.key,
            name=t.name,
            kind=self.kind,
            tier=ProbeTier.ATS,
            outcome=outcome,
            http_status=response.status or None,
            item_count=len(postings),
            elapsed_ms=response.elapsed_ms,
            sample_title=_first_title(postings, "text", "title"),
            detail=detail,
        )
