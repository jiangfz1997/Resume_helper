"""jobspy-backed adapter for Indeed and LinkedIn.

Unlike Workday, jobspy already returns full posting data (including
description) from one scrape_jobs() call, so search() does the real work and
caches full rows; fetch_detail() is a pure in-memory lookup afterward, not a
second network request.

jobspy swallows transport failures internally and returns an empty
DataFrame rather than raising -- confirmed against real ZipRecruiter/
Glassdoor blocks in job-discovery/lambda_probe/README.md -- so this module
attaches a handler to jobspy's own loggers (propagate is off; a root handler
sees nothing) and raises SourceBlockedError on a detected block instead of
silently returning zero refs, which would otherwise be indistinguishable
from "no matching jobs."
"""

from __future__ import annotations

import logging
import math
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from job_discovery.domain.models import SearchQuery, SourceJobObservation, SourceJobRef, SourceName

_BLOCK_LOG_MARKERS = (
    "status code 401",
    "status code 403",
    "status code 429",
    "forbidden",
    "captcha",
    "blocked",
    "too many requests",
    "rate limit",
)

_INDEED_JK_RE = re.compile(r"[?&]jk=([a-zA-Z0-9]+)")
_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)")


class SourceBlockedError(RuntimeError):
    pass


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text


def _extract_source_job_id(job_url: str, site_name: str) -> str:
    if site_name == "indeed":
        match = _INDEED_JK_RE.search(job_url)
        if match:
            return match.group(1)
    elif site_name == "linkedin":
        match = _LINKEDIN_ID_RE.search(job_url)
        if match:
            return match.group(1)
    return job_url


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(f"{record.levelname}: {record.getMessage()}")


def _jobspy_loggers() -> list[logging.Logger]:
    names = [name for name in list(logging.Logger.manager.loggerDict) if name.lower().startswith("jobspy")]
    return [logging.getLogger(name) for name in names]


@contextmanager
def _capture_jobspy_logs() -> Iterator[list[str]]:
    handler = _LogCapture()
    loggers = _jobspy_loggers()
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        if lg.level > logging.DEBUG:
            lg.setLevel(logging.DEBUG)
    try:
        yield handler.messages
    finally:
        for lg, level in zip(loggers, levels):
            lg.removeHandler(handler)
            lg.setLevel(level)


def _block_signal(messages: list[str]) -> str | None:
    for message in messages:
        lowered = message.lower()
        if any(marker in lowered for marker in _BLOCK_LOG_MARKERS):
            return message[:300]
    return None


def _row_to_observation(row: dict[str, Any], ref: SourceJobRef, observed_at: datetime) -> SourceJobObservation:
    """job_url_direct, when present, is the real ATS destination (Workday,
    Greenhouse, ...) -- the same signal that let the TD posting merge across
    Indeed and Workday in the Lambda probe. Prefer it over job_url, jobspy's
    own listing page, which never matches an ATS-native apply URL."""
    apply_url = _clean(row.get("job_url_direct")) or _clean(row.get("job_url"))
    workplace_hint = "remote" if row.get("is_remote") is True else None

    return SourceJobObservation(
        source=ref.source,
        source_job_id=ref.source_job_id,
        source_url=ref.source_url,
        apply_url_raw=apply_url,
        title_raw=_clean(row.get("title")) or "",
        company_raw=_clean(row.get("company")) or "",
        location_raw=_clean(row.get("location")),
        workplace_type_raw=workplace_hint,
        posted_at_raw=_clean(row.get("date_posted")),
        description_raw=_clean(row.get("description")),
        salary_text_raw=None,
        observed_at=observed_at,
        run_id=ref.run_id,
    )


class JobSpySource:
    """One instance per site (Indeed or LinkedIn)."""

    def __init__(self, source: SourceName, site_name: str, country_indeed: str = "canada") -> None:
        self.source = source
        self.site_name = site_name
        self.country_indeed = country_indeed
        self._rows: dict[str, dict[str, Any]] = {}

    def search(self, query: SearchQuery) -> list[SourceJobRef]:
        from jobspy import scrape_jobs

        kwargs: dict[str, Any] = {
            "site_name": [self.site_name],
            "search_term": query.query,
            "location": query.location,
            "results_wanted": query.max_results,
            "hours_old": query.hours_old,
            "description_format": "markdown",
        }
        if self.site_name == "indeed":
            kwargs["country_indeed"] = self.country_indeed
        if self.site_name == "linkedin":
            kwargs["linkedin_fetch_description"] = True

        with _capture_jobspy_logs() as messages:
            frame = scrape_jobs(**kwargs)
            blocked = _block_signal(messages)

        if blocked is not None:
            raise SourceBlockedError(f"{self.site_name}: {blocked}")

        refs: list[SourceJobRef] = []
        if frame is None or len(frame) == 0:
            return refs

        for _, row in frame.iterrows():
            row_dict = row.to_dict()
            job_url = _clean(row_dict.get("job_url")) or ""
            if not job_url:
                continue
            source_job_id = _extract_source_job_id(job_url, self.site_name)
            self._rows[source_job_id] = row_dict
            refs.append(
                SourceJobRef(source=self.source, source_job_id=source_job_id, source_url=job_url, run_id=query.run_id)
            )
        return refs

    def fetch_detail(self, ref: SourceJobRef) -> SourceJobObservation:
        row = self._rows.get(ref.source_job_id)
        if row is None:
            raise KeyError(f"{ref.source_job_id} was not returned by the most recent search()")
        return _row_to_observation(row, ref, observed_at=datetime.now(timezone.utc))
