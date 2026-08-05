"""Workday CXS adapter.

Endpoint shapes below were confirmed directly against
td.wd3.myworkdayjobs.com (see tests/fixtures/workday/) -- reimplemented from
that live response, not copied from ApplyPilot, which is AGPL-3.0-only. See
job-discovery/README.md's licensing note.

Split deliberately into network I/O (WorkdaySource) and pure parsing
(_parse_search_response / _parse_detail_response) so unit tests replay a
saved fixture instead of hitting the real site -- architecture doc 9.4:
tests should not depend on a live network by default.
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from job_discovery.domain.models import SearchQuery, SourceJobObservation, SourceJobRef, SourceName

_USER_AGENT = "Mozilla/5.0 (compatible; job-discovery/0.1)"


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        joined = "\n".join(chunk.strip() for chunk in self._chunks if chunk.strip())
        return re.sub(r"\n{3,}", "\n\n", joined)


def strip_html(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    return parser.text()


def _request_json(url: str, payload: dict[str, Any] | None, timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _USER_AGENT)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _parse_search_response(
    body: dict[str, Any], *, employer_key: str, base_url: str, site_id: str, run_id: str
) -> list[SourceJobRef]:
    refs: list[SourceJobRef] = []
    for posting in body.get("jobPostings", []):
        external_path = posting.get("externalPath")
        if not external_path:
            continue
        refs.append(
            SourceJobRef(
                source=SourceName.WORKDAY,
                source_job_id=f"{employer_key}:{external_path}",
                source_url=f"{base_url}/{site_id}{external_path}",
                run_id=run_id,
            )
        )
    return refs


def _parse_detail_response(
    body: dict[str, Any], *, ref: SourceJobRef, employer_name: str, observed_at: datetime
) -> SourceJobObservation:
    info = body["jobPostingInfo"]
    description_html = info.get("jobDescription") or ""
    return SourceJobObservation(
        source=SourceName.WORKDAY,
        source_job_id=ref.source_job_id,
        source_url=ref.source_url,
        apply_url_raw=info.get("externalUrl"),
        title_raw=info.get("title", ""),
        company_raw=employer_name,
        location_raw=info.get("location"),
        workplace_type_raw=info.get("remoteType"),
        posted_at_raw=info.get("postedOn"),
        description_raw=strip_html(description_html) if description_html else None,
        salary_text_raw=None,
        observed_at=observed_at,
        run_id=ref.run_id,
    )


class WorkdaySource:
    """One instance per employer. Workday task granularity is
    employer x query, not one adapter scanning every tenant in a registry --
    see architecture doc 4.3."""

    source = SourceName.WORKDAY

    def __init__(self, employer_key: str, employer_name: str, tenant: str, site_id: str, base_url: str) -> None:
        self.employer_key = employer_key
        self.employer_name = employer_name
        self.tenant = tenant
        self.site_id = site_id
        self.base_url = base_url.rstrip("/")

    def search(self, query: SearchQuery) -> list[SourceJobRef]:
        url = f"{self.base_url}/wday/cxs/{self.tenant}/{self.site_id}/jobs"
        payload = {"appliedFacets": {}, "limit": query.max_results, "offset": 0, "searchText": query.query}
        body = _request_json(url, payload)
        return _parse_search_response(
            body,
            employer_key=self.employer_key,
            base_url=self.base_url,
            site_id=self.site_id,
            run_id=query.run_id,
        )

    def fetch_detail(self, ref: SourceJobRef) -> SourceJobObservation:
        external_path = ref.source_job_id.split(":", 1)[1]
        url = f"{self.base_url}/wday/cxs/{self.tenant}/{self.site_id}{external_path}"
        body = _request_json(url, None)
        return _parse_detail_response(
            body, ref=ref, employer_name=self.employer_name, observed_at=datetime.now(timezone.utc)
        )
