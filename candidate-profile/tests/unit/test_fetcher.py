from __future__ import annotations

import json

import pytest

from candidate_profile.domain.models import FetchStrategy
from candidate_profile.extraction import fetcher as fetcher_module
from candidate_profile.extraction.fetcher import (
    CompositePageFetcher,
    HttpPageFetcher,
    PageFetchError,
    WorkdayPageFetcher,
    html_to_text,
    to_cxs_url,
)

BMO_URL = (
    "https://bmo.wd3.myworkdayjobs.com/en-US/External/job/Toronto-ON-CAN/"
    "Software-Developer--New-or-Recent-Graduate-_R260020222?source=Social_Linkedin"
)


@pytest.fixture
def captured_get(monkeypatch):
    """Replace the module's single HTTP entry point and record what it saw."""
    calls: list[tuple[str, str | None]] = []
    responses: dict[str, str] = {}

    def fake_get(url: str, timeout: int, accept: str | None = None) -> tuple[str, str]:
        del timeout
        calls.append((url, accept))
        if url not in responses:
            raise AssertionError(f"unexpected fetch: {url}")
        return responses[url], url

    monkeypatch.setattr(fetcher_module, "_get", fake_get)
    return calls, responses


class TestToCxsUrl:
    def test_rewrites_a_real_posting_url(self):
        assert to_cxs_url(BMO_URL) == (
            "https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/job/"
            "Toronto-ON-CAN/Software-Developer--New-or-Recent-Graduate-_R260020222"
        )

    def test_drops_the_query_string(self):
        assert "?" not in to_cxs_url(BMO_URL)

    def test_locale_segment_is_optional(self):
        without_locale = "https://bmo.wd3.myworkdayjobs.com/External/job/Toronto-ON-CAN/Role_R1"
        assert to_cxs_url(without_locale).endswith("/wday/cxs/bmo/External/job/Toronto-ON-CAN/Role_R1")

    def test_details_segment_is_renamed_to_job(self):
        """Newer Workday links say /details/ where the API says /job/."""
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Careers/details/Some-Role_R9"
        assert to_cxs_url(url).endswith("/wday/cxs/acme/Careers/job/Some-Role_R9")

    def test_an_already_rewritten_url_is_left_alone(self):
        cxs = "https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/job/Toronto-ON-CAN/Role_R1"
        assert to_cxs_url(cxs) == cxs

    def test_rejects_a_non_workday_host(self):
        with pytest.raises(PageFetchError, match="not a Workday URL"):
            to_cxs_url("https://www.linkedin.com/jobs/view/123/")

    def test_rejects_a_url_with_no_site_id(self):
        with pytest.raises(PageFetchError, match="cannot locate site id"):
            to_cxs_url("https://bmo.wd3.myworkdayjobs.com/en-US")


class TestHandles:
    @pytest.mark.parametrize(
        "url",
        [
            BMO_URL,
            "https://acme.wd1.myworkdayjobs.com/Careers/job/Role_R1",
            "https://acme.wd103.myworkdayjobs.com/x/job/y",
        ],
    )
    def test_recognises_workday_hosts(self, url):
        assert WorkdayPageFetcher.handles(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/jobs/view/123/",
            "https://boards.greenhouse.io/acme/jobs/1",
            # Substring, not a suffix -- must not match.
            "https://myworkdayjobs.com.evil.test/job/1",
        ],
    )
    def test_ignores_everything_else(self, url):
        assert not WorkdayPageFetcher.handles(url)


class TestWorkdayPageFetcher:
    def test_reads_title_location_and_description(self, captured_get):
        calls, responses = captured_get
        cxs = to_cxs_url(BMO_URL)
        responses[cxs] = json.dumps(
            {
                "jobPostingInfo": {
                    "title": "Software Developer (New or Recent Graduate)",
                    "location": "Toronto, ON, CAN",
                    "timeType": "Full time",
                    "jobDescription": "<div><p>Build <b>things</b>.</p><p>5+ years.</p></div>",
                }
            }
        )

        page = WorkdayPageFetcher().load(BMO_URL)

        assert calls == [(cxs, "application/json")]
        assert page.fetch_strategy is FetchStrategy.WORKDAY_CXS
        assert page.text.startswith("Software Developer (New or Recent Graduate)\nToronto, ON, CAN")
        assert "Build" in page.text and "5+ years." in page.text

    def test_missing_header_fields_are_skipped_not_rendered_as_none(self, captured_get):
        _, responses = captured_get
        responses[to_cxs_url(BMO_URL)] = json.dumps(
            {"jobPostingInfo": {"title": None, "location": "", "jobDescription": "<p>Body text.</p>"}}
        )

        page = WorkdayPageFetcher().load(BMO_URL)

        assert page.text == "Body text."

    def test_an_empty_description_is_an_error_not_an_empty_page(self, captured_get):
        """The old failure mode was a blank jd_text saved as a success."""
        _, responses = captured_get
        responses[to_cxs_url(BMO_URL)] = json.dumps({"jobPostingInfo": {"jobDescription": ""}})

        with pytest.raises(PageFetchError, match="no description"):
            WorkdayPageFetcher().load(BMO_URL)

    def test_a_missing_job_posting_info_key_is_an_error(self, captured_get):
        _, responses = captured_get
        responses[to_cxs_url(BMO_URL)] = json.dumps({"userAuthenticated": False})

        with pytest.raises(PageFetchError, match="no description"):
            WorkdayPageFetcher().load(BMO_URL)

    def test_non_json_body_reports_the_original_url(self, captured_get):
        _, responses = captured_get
        responses[to_cxs_url(BMO_URL)] = "<html>login</html>"

        with pytest.raises(PageFetchError, match="non-JSON"):
            WorkdayPageFetcher().load(BMO_URL)


class TestHttpPageFetcher:
    def test_detags_and_keeps_a_snapshot(self, captured_get):
        calls, responses = captured_get
        url = "https://boards.greenhouse.io/acme/jobs/1"
        responses[url] = "<html><body><script>var x=1;</script><p>Hello</p></body></html>"

        page = HttpPageFetcher().load(url)

        assert calls == [(url, None)]
        assert page.text == "Hello"
        assert page.fetch_strategy is FetchStrategy.HTML
        assert "<script>" not in page.raw_html


class TestCompositePageFetcher:
    def test_workday_urls_go_to_the_json_endpoint(self, captured_get):
        calls, responses = captured_get
        responses[to_cxs_url(BMO_URL)] = json.dumps(
            {"jobPostingInfo": {"title": "Dev", "jobDescription": "<p>Body.</p>"}}
        )

        page = CompositePageFetcher().load(BMO_URL)

        assert page.fetch_strategy is FetchStrategy.WORKDAY_CXS
        assert calls[0][0].startswith("https://bmo.wd3.myworkdayjobs.com/wday/cxs/")

    def test_other_urls_are_fetched_as_html(self, captured_get):
        calls, responses = captured_get
        url = "https://www.linkedin.com/jobs/view/123/"
        responses[url] = "<html><body><p>JD body</p></body></html>"

        page = CompositePageFetcher().load(url)

        assert page.fetch_strategy is FetchStrategy.HTML
        assert calls == [(url, None)]


class TestHtmlToText:
    def test_the_spa_shell_that_caused_the_bug_still_yields_nothing(self):
        """A Workday page body is an empty div plus scripts. Confirms the
        generic reader genuinely cannot serve these, which is why the
        Workday branch exists rather than a retry."""
        shell = '<html><head><title>x</title></head><body><div id="root"></div><script>boot();</script></body></html>'
        assert html_to_text(shell).strip() == ""
