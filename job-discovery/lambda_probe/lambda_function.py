"""One-shot Lambda probe: Indeed + LinkedIn, last 24h, one search term.

Self-contained on purpose. It does not import the probes package so the
deployment zip carries only what the function needs.

Event overrides (all optional):
    {"search_term": "Software Engineer", "location": "Toronto, ON",
     "hours_old": 24, "results_wanted": 20, "sites": ["indeed", "linkedin"]}
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from pydantic import BaseModel, Field

log = logging.getLogger()
log.setLevel(logging.INFO)

DEFAULT_SITES: list[str] = ["indeed", "linkedin"]

# jobspy swallows transport failures and returns an empty DataFrame instead of
# raising. The status code only reaches its own loggers, which have propagation
# disabled, so an empty result is otherwise indistinguishable from a block.
BLOCK_LOG_MARKERS: tuple[str, ...] = (
    "status code 401",
    "status code 403",
    "status code 429",
    "forbidden",
    "captcha",
    "blocked",
    "too many requests",
    "rate limit",
)


class ProbeRequest(BaseModel):
    search_term: str = "Software Engineer"
    location: str = "Toronto, ON"
    hours_old: int = 24
    results_wanted: int = 20
    country_indeed: str = "canada"
    sites: list[str] = Field(default_factory=lambda: list(DEFAULT_SITES))


class JobRow(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    date_posted: str | None = None
    job_url: str | None = None
    job_url_direct: str | None = None
    is_remote: bool | None = None
    description_chars: int = 0


class SiteResult(BaseModel):
    site: str
    status: str
    row_count: int = 0
    elapsed_ms: int = 0
    detail: str | None = None
    jobs: list[JobRow] = Field(default_factory=list)


class ProbeResponse(BaseModel):
    request: ProbeRequest
    egress_ip: str | None = None
    total_rows: int = 0
    results: list[SiteResult] = Field(default_factory=list)
    s3_key: str | None = None


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(f"{record.levelname}: {record.getMessage()}")


@contextmanager
def _capture_jobspy_logs() -> Iterator[list[str]]:
    handler = _LogCapture()
    names = [n for n in list(logging.Logger.manager.loggerDict) if n.lower().startswith("jobspy")]
    loggers = [logging.getLogger(n) for n in names]
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
        if any(marker in lowered for marker in BLOCK_LOG_MARKERS):
            return message[:300]
    return None


def _egress_ip() -> str | None:
    import urllib.request

    try:
        with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5) as resp:
            return resp.read().decode().strip()
    except Exception:
        return None


def _to_rows(frame: Any, limit: int) -> list[JobRow]:
    rows: list[JobRow] = []
    for _, record in frame.head(limit).iterrows():
        description = record.get("description")
        rows.append(
            JobRow(
                title=_str_or_none(record.get("title")),
                company=_str_or_none(record.get("company")),
                location=_str_or_none(record.get("location")),
                date_posted=_str_or_none(record.get("date_posted")),
                job_url=_str_or_none(record.get("job_url")),
                job_url_direct=_str_or_none(record.get("job_url_direct")),
                is_remote=bool(record.get("is_remote")) if record.get("is_remote") is not None else None,
                description_chars=len(description) if isinstance(description, str) else 0,
            )
        )
    return rows


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    return text


def scrape_site(site: str, request: ProbeRequest) -> SiteResult:
    from jobspy import scrape_jobs

    kwargs: dict[str, Any] = {
        "site_name": [site],
        "search_term": request.search_term,
        "location": request.location,
        "results_wanted": request.results_wanted,
        "hours_old": request.hours_old,
        "description_format": "markdown",
    }
    if site == "indeed":
        kwargs["country_indeed"] = request.country_indeed
    if site == "linkedin":
        kwargs["linkedin_fetch_description"] = True

    started = time.perf_counter()
    with _capture_jobspy_logs() as messages:
        try:
            frame = scrape_jobs(**kwargs)
        except Exception as exc:
            return SiteResult(
                site=site,
                status="exception",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                detail=f"{type(exc).__name__}: {exc}"[:400],
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        blocked = _block_signal(messages)
        error = next((m for m in messages if m.startswith("ERROR")), None)

    count = 0 if frame is None else int(len(frame))
    if blocked is not None:
        return SiteResult(site=site, status="blocked", row_count=count, elapsed_ms=elapsed_ms, detail=blocked)
    if count == 0:
        return SiteResult(
            site=site,
            status="error" if error else "empty",
            elapsed_ms=elapsed_ms,
            detail=(error or "no rows and no error logged")[:300],
        )
    return SiteResult(
        site=site,
        status="ok",
        row_count=count,
        elapsed_ms=elapsed_ms,
        jobs=_to_rows(frame, limit=request.results_wanted),
    )


def _put_s3(payload: str) -> str | None:
    bucket = os.environ.get("RESULT_BUCKET")
    if not bucket:
        return None
    try:
        import boto3

        key = f"lambda-probe/{int(time.time())}.json"
        boto3.client("s3").put_object(
            Bucket=bucket, Key=key, Body=payload.encode("utf-8"), ContentType="application/json"
        )
        return f"s3://{bucket}/{key}"
    except Exception as exc:
        log.warning("s3 upload skipped: %s", exc)
        return None


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    request = ProbeRequest.model_validate(event or {})
    log.info("probe start: %s", request.model_dump_json())

    results = [scrape_site(site, request) for site in request.sites]
    response = ProbeResponse(
        request=request,
        egress_ip=_egress_ip(),
        total_rows=sum(r.row_count for r in results),
        results=results,
    )
    response.s3_key = _put_s3(response.model_dump_json(indent=2))

    for result in results:
        log.info(
            "%s: %s rows=%d %dms %s",
            result.site,
            result.status,
            result.row_count,
            result.elapsed_ms,
            result.detail or "",
        )
    return json.loads(response.model_dump_json())


if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2, ensure_ascii=False))
