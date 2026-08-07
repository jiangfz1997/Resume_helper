"""Plain stdlib HTTP fetch + HTML-to-text, no bs4/lxml -- keeps the extract
Lambda's package small, consistent with gemini_scorer.py's use of urllib
instead of an SDK.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}


class PageFetchError(RuntimeError):
    pass


class HttpPageFetcher:
    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; ApplicationTrackerBot/1.0)"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PageFetchError(str(exc)) from exc


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
