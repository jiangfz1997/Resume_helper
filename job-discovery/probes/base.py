"""Prober interface and shared HTTP helpers.

Tier A probers depend on the standard library only, so this module must not
import jobspy, pandas or httpx at module scope.
"""

from __future__ import annotations

import abc
import json
import time
import urllib.error
import urllib.request
from typing import Any, ClassVar

from probes.models import ProbeOutcome, ProbeResult, ProbeTarget

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BLOCK_STATUSES = frozenset({401, 403, 407, 429, 451})
BLOCK_MARKERS = ("captcha", "are you a human", "unusual traffic", "access denied", "cf-browser-verification")


class HttpResponse:
    """Minimal transport result so probers never branch on urllib exceptions."""

    def __init__(self, status: int, body: bytes, elapsed_ms: int, error: str | None = None) -> None:
        self.status: int = status
        self.body: bytes = body
        self.elapsed_ms: int = elapsed_ms
        self.error: str | None = error

    def json(self) -> Any:
        return json.loads(self.body)

    @property
    def text_head(self) -> str:
        return self.body[:2000].decode("utf-8", errors="replace").lower()


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 25,
) -> HttpResponse:
    """POST when payload is given, otherwise GET. Never raises on HTTP errors."""
    data: bytes | None = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    if data:
        req.add_header("Content-Type", "application/json")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return HttpResponse(resp.status, body, _ms_since(started))
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return HttpResponse(exc.code, body, _ms_since(started), error=str(exc.reason))
    except Exception as exc:
        return HttpResponse(0, b"", _ms_since(started), error=f"{type(exc).__name__}: {exc}")


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def classify_http(response: HttpResponse, item_count: int) -> tuple[ProbeOutcome, str | None]:
    """Map a transport result onto a probe verdict."""
    if response.status == 0:
        return ProbeOutcome.ERROR, response.error
    if response.status in (404, 410):
        return ProbeOutcome.NOT_FOUND, "target token or path is stale, not an IP block"
    if response.status in BLOCK_STATUSES:
        return ProbeOutcome.BLOCKED, f"HTTP {response.status} {response.error or ''}".strip()
    if response.status >= 400:
        return ProbeOutcome.ERROR, f"HTTP {response.status} {response.error or ''}".strip()

    marker = next((m for m in BLOCK_MARKERS if m in response.text_head), None)
    if marker is not None:
        return ProbeOutcome.BLOCKED, f"200 response contains challenge marker: {marker}"

    if item_count == 0:
        return ProbeOutcome.EMPTY, "HTTP 200 but zero postings parsed"
    return ProbeOutcome.OK, None


class Prober(abc.ABC):
    """One probe strategy per source family."""

    kind: ClassVar[str]

    @abc.abstractmethod
    def probe(self, target: ProbeTarget) -> ProbeResult:
        """Execute a single reachability check. Must never raise."""
        raise NotImplementedError
