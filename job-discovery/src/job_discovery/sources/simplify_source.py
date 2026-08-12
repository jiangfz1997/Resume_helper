"""Adapters for Simplify's two curated new-grad feeds.

The Canada page and GitHub repository are maintained by the same ecosystem,
but they are not identical datasets: the page is a broad Canada-only list,
while the repository is a worldwide, tech-heavy community list. They remain
separate SourceName values so the dashboard can expose either feed on its own;
the normal apply-URL/description dedup pipeline merges overlapping postings.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import urllib.error
from urllib.parse import urlencode, urljoin
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable

from job_discovery.domain.models import SearchQuery, SourceJobObservation, SourceJobRef, SourceName

CANADA_LIST_URL = "https://simplify.jobs/l/New-Grad-Jobs-Canada"
GITHUB_REPO_URL = "https://github.com/SimplifyJobs/New-Grad-Positions"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"
_USER_AGENT = "Mozilla/5.0 (compatible; ResumeHelper-job-discovery/0.1)"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_AGE_RE = re.compile(r"^(\d+)d$", re.IGNORECASE)
_LIST_BUNDLE_RE = re.compile(r'src="([^"]*pages/l/[^"]+\.js[^"]*)"')
_TYPESENSE_CONFIG_RE = re.compile(
    r'apiKey:"([^"]+)".*?nearestNode:\{host:"([^"]+)"', re.DOTALL
)
_CANADA_LOCATION_RE = re.compile(
    r"(?:"
    r"\bcanada\b|\bcanadian\b|"
    r"\b(?:alberta|british columbia|manitoba|new brunswick|newfoundland(?: and labrador)?|"
    r"nova scotia|ontario|prince edward island|qu[eé]bec|saskatchewan|"
    r"northwest territories|nunavut|yukon)\b|"
    r"(?:^|,\s*)(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)(?=\s*(?:,|$))"
    r")",
    re.IGNORECASE,
)


def _request_text(url: str, timeout: int = 30, headers: dict[str, str] | None = None) -> str:
    request_headers = {"Accept": "text/html", "User-Agent": _USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _resolve_apply_url(click_url: str, timeout: int = 15) -> str:
    """Resolve only Simplify's first redirect; do not crawl the destination ATS."""
    request = urllib.request.Request(click_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            return response.geturl()
    except urllib.error.HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
            return urljoin(click_url, exc.headers["Location"])
        raise


def _next_page_props(html: str) -> dict[str, Any]:
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        raise ValueError("Simplify page did not contain __NEXT_DATA__")
    return json.loads(match.group(1))["props"]["pageProps"]


def _all_canada_rows(page_html: str, list_id: str, max_results: int) -> list[dict[str, Any]]:
    """Use the same public, search-only Typesense client as the rendered page.

    The key is intentionally discovered from the current public JS bundle
    instead of being checked into this repository. If the bundle layout
    changes, callers safely fall back to the 30 server-rendered rows.
    """
    bundle_match = _LIST_BUNDLE_RE.search(page_html)
    if bundle_match is None:
        raise ValueError("Simplify list bundle was not present")
    bundle = _request_text(urljoin(CANADA_LIST_URL, bundle_match.group(1)))
    config_match = _TYPESENSE_CONFIG_RE.search(bundle)
    if config_match is None:
        raise ValueError("Simplify public search configuration was not present")
    api_key, host = config_match.groups()
    rows: list[dict[str, Any]] = []
    page = 1
    while len(rows) < max_results:
        per_page = min(250, max_results - len(rows))
        params = urlencode({
            "q": "*",
            "query_by": "title,company_name,locations",
            "filter_by": f"job_lists:'{list_id}'",
            "sort_by": "_text_match:desc,updated_date:desc,posting_id:desc",
            "per_page": per_page,
            "page": page,
        })
        payload = json.loads(_request_text(
            f"https://{host}/collections/jobs/documents/search?{params}",
            headers={"Accept": "application/json", "X-TYPESENSE-API-KEY": api_key},
        ))
        batch = [hit["document"] for hit in payload.get("hits", []) if hit.get("document")]
        rows.extend(batch)
        if not batch or len(rows) >= int(payload.get("found", len(rows))):
            break
        page += 1
    return rows[:max_results]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.chunks)


def _strip_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return parser.text()


def _salary_text(row: dict[str, Any]) -> str | None:
    minimum, maximum = row.get("min_salary"), row.get("max_salary")
    if minimum is None and maximum is None:
        return None
    currency = row.get("currency_type") or ""
    if minimum == maximum:
        amount = f"{minimum:g}"
    else:
        low = f"{minimum:g}" if minimum is not None else "?"
        high = f"{maximum:g}" if maximum is not None else "?"
        amount = f"{low}–{high}"
    return f"{currency} {amount}".strip()


class SimplifyCanadaSource:
    source = SourceName.SIMPLIFY_CANADA

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def search(self, query: SearchQuery) -> list[SourceJobRef]:
        page_html = _request_text(CANADA_LIST_URL)
        page_props = _next_page_props(page_html)
        rows = page_props.get("initialJobHits", [])
        if query.max_results > len(rows):
            try:
                rows = _all_canada_rows(page_html, page_props["jobList"]["id"], query.max_results)
            except Exception:
                # A changed client bundle must not turn a useful 30-row feed
                # into a total outage; the Lambda report still shows what ran.
                pass
        refs: list[SourceJobRef] = []
        for row in rows[: query.max_results]:
            source_job_id = str(row.get("id") or row.get("objectID") or "").strip()
            if not source_job_id:
                continue
            self._rows[source_job_id] = row
            refs.append(SourceJobRef(
                source=self.source,
                source_job_id=source_job_id,
                source_url=f"https://simplify.jobs/p/{source_job_id}",
                run_id=query.run_id,
            ))
        return refs

    def summary(self, ref: SourceJobRef) -> dict[str, Any]:
        return self._rows[ref.source_job_id]

    def fetch_detail(self, ref: SourceJobRef) -> SourceJobObservation:
        summary = self._rows.get(ref.source_job_id)
        if summary is None:
            raise KeyError(f"{ref.source_job_id} was not returned by search()")
        posting = _next_page_props(_request_text(ref.source_url))["jobPosting"]
        company = posting.get("job", {}).get("company", {}).get("name") or summary.get("company_name") or ""
        locations = posting.get("locations") or []
        location = ", ".join(
            str(item.get("value") if isinstance(item, dict) else item) for item in locations
        ) or ", ".join(summary.get("locations") or [])
        return SourceJobObservation(
            source=self.source,
            source_job_id=ref.source_job_id,
            source_url=ref.source_url,
            apply_url_raw=_resolve_apply_url(posting["url"]) if posting.get("url") else None,
            title_raw=posting.get("title") or summary.get("title") or "",
            company_raw=company,
            location_raw=location or None,
            workplace_type_raw=summary.get("travel_requirements"),
            posted_at_raw=posting.get("start_date"),
            description_raw=_strip_html(posting.get("description") or "") or None,
            salary_text_raw=_salary_text(posting),
            new_grad_hint="curated:simplify-canada",
            observed_at=datetime.now(timezone.utc),
            run_id=ref.run_id,
        )


class _GitHubTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = {"text": [], "hrefs": [], "alts": []}
        elif self._cell is not None and tag == "a" and attrs_dict.get("href"):
            self._cell["hrefs"].append(attrs_dict["href"])
        elif self._cell is not None and tag == "img" and attrs_dict.get("alt"):
            self._cell["alts"].append(attrs_dict["alt"])
        elif self._cell is not None and tag == "br":
            self._cell["text"].append(", ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None and data.strip():
            self._cell["text"].append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join(self._cell["text"]).replace(" , ", ", ").strip()
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) >= 5:
                self.rows.append(self._row)
            self._row = None


def _is_canada_location(location: str) -> bool:
    """Require an explicit Canadian country/province marker.

    In particular, bare ``CA`` is California in this feed and bare Remote is
    worldwide/unspecified, so neither is accepted as Canada.
    """
    return _CANADA_LOCATION_RE.search(location) is not None


def _parse_github_rows(
    readme: str,
    max_results: int,
    location_predicate: Callable[[str], bool] | None = None,
) -> list[dict[str, str]]:
    parser = _GitHubTableParser()
    parser.feed(readme)
    results: list[dict[str, str]] = []
    previous_company = ""
    for cells in parser.rows:
        company = str(cells[0]["text"])
        if company == "↳":
            company = previous_company
        elif company:
            company = re.sub(r"^[🔥\s]+", "", company)
            previous_company = company
        title, location, age = (str(cells[index]["text"]) for index in (1, 2, 4))
        hrefs = [str(url) for url in cells[3]["hrefs"]]
        apply_url = next((url for url in hrefs if "simplify.jobs/p/" not in url), hrefs[0] if hrefs else "")
        closed = any("closed" in str(alt).casefold() for alt in cells[3]["alts"])
        if not company or not title or not apply_url or closed:
            continue
        match = _AGE_RE.match(age)
        posted = f"{match.group(1)} days ago" if match else age
        source_job_id = hashlib.sha256(apply_url.encode()).hexdigest()[:32]
        row = {
            "source_job_id": source_job_id,
            "company": company,
            "title": title,
            "location": location,
            "apply_url": apply_url,
            "posted": posted,
        }
        if location_predicate is not None and not location_predicate(location):
            continue
        results.append(row)
        if len(results) >= max_results:
            break
    return results


class SimplifyGitHubSource:
    source = SourceName.SIMPLIFY_GITHUB

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, str]] = {}

    def search(self, query: SearchQuery) -> list[SourceJobRef]:
        rows = _parse_github_rows(
            _request_text(GITHUB_RAW_URL),
            query.max_results,
            location_predicate=_is_canada_location,
        )
        refs: list[SourceJobRef] = []
        for row in rows:
            source_job_id = row["source_job_id"]
            self._rows[source_job_id] = row
            refs.append(SourceJobRef(
                source=self.source,
                source_job_id=source_job_id,
                source_url=GITHUB_REPO_URL,
                run_id=query.run_id,
            ))
        return refs

    def summary(self, ref: SourceJobRef) -> dict[str, str]:
        return self._rows[ref.source_job_id]

    def fetch_detail(self, ref: SourceJobRef) -> SourceJobObservation:
        row = self._rows.get(ref.source_job_id)
        if row is None:
            raise KeyError(f"{ref.source_job_id} was not returned by search()")
        return SourceJobObservation(
            source=self.source,
            source_job_id=ref.source_job_id,
            source_url=ref.source_url,
            apply_url_raw=row["apply_url"],
            title_raw=row["title"],
            company_raw=row["company"],
            location_raw=row["location"],
            posted_at_raw=row["posted"],
            description_raw=None,
            new_grad_hint="curated:simplify-github",
            observed_at=datetime.now(timezone.utc),
            run_id=ref.run_id,
        )
