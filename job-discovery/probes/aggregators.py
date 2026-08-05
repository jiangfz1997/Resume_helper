"""Tier B prober: aggregator sites, exercised through jobspy itself.

Hand-rolled HTTP against Indeed/LinkedIn/Glassdoor would understate what the
real crawler can reach, because jobspy relies on curl_cffi TLS impersonation.
Probing any other way produces false positives for "blocked".
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, ClassVar, Iterator, cast

from probes.base import BLOCK_MARKERS, Prober
from probes.models import AggregatorTarget, ProbeOutcome, ProbeResult, ProbeTarget, ProbeTier

BLOCK_EXCEPTION_MARKERS = (
    "403",
    "429",
    "captcha",
    "blocked",
    "forbidden",
    "too many requests",
    "proxy",
    "challenge",
)

# jobspy catches transport failures internally and still returns an empty
# DataFrame, so the return value alone cannot distinguish "blocked" from
# "no matching jobs". Its log records carry the status code; capture them.
BLOCK_LOG_MARKERS = (
    "status code 403",
    "status code 401",
    "status code 429",
    "forbidden",
    "captcha",
    "blocked",
    "too many requests",
    "rate limit",
)


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(f"{record.levelname}: {record.getMessage()}")


def _jobspy_loggers() -> list[logging.Logger]:
    """jobspy names its loggers "JobSpy:<Site>" and disables propagation,
    so a handler on the root logger never sees them."""
    names = [
        name
        for name in list(logging.Logger.manager.loggerDict)
        if name.lower().startswith("jobspy")
    ]
    return [logging.getLogger(name) for name in names]


@contextmanager
def _capture_jobspy_logs() -> Iterator[list[str]]:
    handler = _LogCapture()
    targets = _jobspy_loggers()
    previous_levels: list[int] = [logger.level for logger in targets]
    for logger in targets:
        logger.addHandler(handler)
        if logger.level > logging.DEBUG:
            logger.setLevel(logging.DEBUG)
    try:
        yield handler.messages
    finally:
        for logger, level in zip(targets, previous_levels):
            logger.removeHandler(handler)
            logger.setLevel(level)


def _block_signal(messages: list[str]) -> str | None:
    for message in messages:
        lowered = message.lower()
        marker = next((m for m in BLOCK_LOG_MARKERS if m in lowered), None)
        if marker is not None:
            return message[:300]
    return None


def jobspy_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("python-jobspy")
    except Exception:
        return None


class JobSpyProber(Prober):
    """Calls jobspy.scrape_jobs once per target and reports what came back."""

    kind: ClassVar[str] = "aggregator"

    def probe(self, target: ProbeTarget) -> ProbeResult:
        t = cast(AggregatorTarget, target)
        base = {
            "key": t.key,
            "name": t.name,
            "kind": self.kind,
            "tier": ProbeTier.AGGREGATOR,
        }

        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            return ProbeResult(
                **base,
                outcome=ProbeOutcome.SKIPPED,
                detail=f"python-jobspy not installed: {exc}",
            )

        kwargs: dict[str, Any] = {
            "site_name": [t.site],
            "search_term": t.search_term,
            "location": t.location,
            "results_wanted": t.results_wanted,
            "hours_old": t.hours_old,
        }
        if t.site == "indeed":
            kwargs["country_indeed"] = t.country_indeed

        started = time.perf_counter()
        with _capture_jobspy_logs() as messages:
            try:
                frame = scrape_jobs(**kwargs)
            except Exception as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                message = f"{type(exc).__name__}: {exc}"
                lowered = message.lower()
                blocked = any(m in lowered for m in BLOCK_EXCEPTION_MARKERS) or any(
                    m in lowered for m in BLOCK_MARKERS
                )
                return ProbeResult(
                    **base,
                    outcome=ProbeOutcome.BLOCKED if blocked else ProbeOutcome.ERROR,
                    elapsed_ms=elapsed,
                    detail=message[:400],
                )

            elapsed = int((time.perf_counter() - started) * 1000)
            block_signal = _block_signal(messages)
            error_signal = next((m for m in messages if m.startswith("ERROR")), None)

        count = 0 if frame is None else int(len(frame))
        sample: str | None = None
        if count > 0:
            try:
                sample = str(frame.iloc[0].get("title"))[:120]
            except Exception:
                sample = None

        if block_signal is not None:
            return ProbeResult(
                **base,
                outcome=ProbeOutcome.BLOCKED,
                item_count=count,
                elapsed_ms=elapsed,
                sample_title=sample,
                detail=block_signal,
            )

        if count == 0:
            return ProbeResult(
                **base,
                outcome=ProbeOutcome.ERROR if error_signal else ProbeOutcome.EMPTY,
                item_count=0,
                elapsed_ms=elapsed,
                detail=error_signal[:300]
                if error_signal
                else "no rows, no error logged; compare against the baseline run",
            )

        return ProbeResult(
            **base,
            outcome=ProbeOutcome.OK,
            item_count=count,
            elapsed_ms=elapsed,
            sample_title=sample,
        )
