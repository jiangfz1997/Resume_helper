"""Plain stdlib HTTP fetch + HTML-to-text, no bs4/lxml -- keeps the extract
Lambda's package small, consistent with gemini_scorer.py's use of urllib
instead of an SDK.

Workday needs its own reader. Its posting pages are client-rendered: a live
fetch of a real BMO posting returned 20655 bytes of HTML that detagged to
zero characters, which is what "no extractable text found on page" was
reporting. The same posting served over Workday's own JSON endpoint returns
a 7676-character description, so WorkdayPageFetcher rewrites the URL to
/wday/cxs/... rather than trying to squeeze text out of the SPA shell. This
is the same endpoint job_discovery.sources.workday already reads from; that
module gets tenant and site from configuration, while here they have to be
recovered from the URL the user pasted.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

from candidate_profile.domain.models import FetchedPage, FetchStrategy

_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}

_USER_AGENT = "Mozilla/5.0 (compatible; ApplicationTrackerBot/1.0)"

_WORKDAY_HOST_RE = re.compile(r"(?:^|\.)myworkdayjobs\.com$", re.IGNORECASE)
_LOCALE_SEGMENT_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")


class PageFetchError(RuntimeError):
    pass


def _get(url: str, timeout: int, accept: str | None = None) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    if accept:
        request.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace"), response.url
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PageFetchError(str(exc)) from exc


class HttpPageFetcher:
    """Generic reader: whatever HTML the server returns, detagged."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def load(self, url: str) -> FetchedPage:
        html, _ = _get(url, self.timeout)
        return FetchedPage(
            text=html_to_text(html),
            raw_html=strip_non_content_tags(html),
            fetch_strategy=FetchStrategy.HTML,
        )


class WorkdayPageFetcher:
    """Reads a Workday posting through the tenant's cxs JSON endpoint."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    @staticmethod
    def handles(url: str) -> bool:
        return bool(_WORKDAY_HOST_RE.search(urlparse(url).netloc.split(":")[0]))

    def load(self, url: str) -> FetchedPage:
        body, _ = _get(to_cxs_url(url), self.timeout, accept="application/json")
        try:
            info = json.loads(body).get("jobPostingInfo") or {}
        except json.JSONDecodeError as exc:
            raise PageFetchError(f"workday returned non-JSON for {url}") from exc

        description_html = info.get("jobDescription") or ""
        # Title and location are separate JSON fields, never part of the
        # description fragment. Prepending them is what lets the extractor
        # read them back -- on a normal page they would come from the header.
        header = [
            value
            for value in (info.get("title"), info.get("location"), info.get("timeType"))
            if isinstance(value, str) and value.strip()
        ]
        text = "\n".join([*header, html_to_text(description_html)]).strip()
        if not text:
            raise PageFetchError(f"workday posting has no description: {url}")
        return FetchedPage(
            text=text,
            raw_html=strip_non_content_tags(description_html) or None,
            fetch_strategy=FetchStrategy.WORKDAY_CXS,
        )


class CompositePageFetcher:
    """Routes by host, falling back to the generic HTML reader. Add a site
    here rather than teaching HttpPageFetcher about individual employers."""

    def __init__(self, timeout: int = 15) -> None:
        self._workday = WorkdayPageFetcher(timeout)
        self._http = HttpPageFetcher(timeout)

    def load(self, url: str) -> FetchedPage:
        if WorkdayPageFetcher.handles(url):
            return self._workday.load(url)
        return self._http.load(url)


def to_cxs_url(url: str) -> str:
    """Map a human Workday URL onto its JSON endpoint.

        https://bmo.wd3.myworkdayjobs.com/en-US/External/job/Toronto-ON-CAN/Some-Role_R123
        -> https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/job/Toronto-ON-CAN/Some-Role_R123

    The tenant is the first host label and the site id is the first path
    segment after an optional locale. Newer Workday links say /details/
    where the API says /job/, so that segment is renamed.
    """
    parsed = urlparse(url)
    host = parsed.netloc.split(":")[0]
    if not _WORKDAY_HOST_RE.search(host):
        raise PageFetchError(f"not a Workday URL: {url}")

    tenant = host.split(".")[0]
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0].lower() == "wday":
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if segments and _LOCALE_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    if len(segments) < 2:
        raise PageFetchError(f"cannot locate site id in Workday URL: {url}")

    site_id, *rest = segments
    rest = ["job" if segment.lower() == "details" else segment for segment in rest]
    path = "/".join(["wday", "cxs", tenant, site_id, *rest])
    return urlunparse((parsed.scheme, parsed.netloc, f"/{path}", "", "", ""))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self.chunks.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.chunks)


def strip_non_content_tags(html: str) -> str:
    """Best-effort removal of script/style blocks before ``raw_html`` is
    persisted -- not a full sanitizer, just keeps the stored snapshot from
    being dominated by JS bundle bytes that eat into DynamoDB's 400KB item
    cap."""
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
