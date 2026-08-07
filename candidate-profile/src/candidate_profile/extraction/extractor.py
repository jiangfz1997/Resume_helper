"""Gemini-backed metadata extraction. Only pulls company/title/location out
of already-fetched page text -- never touches jd_text itself, since the
whole point of this feature is a faithful copy of the posting, not an
LLM-paraphrased one. Plain REST via urllib, same adapter style as
job_discovery.scoring.gemini_scorer.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from candidate_profile.domain.models import ExtractedJobInfo

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT_TEMPLATE = """The following is the plain-text content of a job posting web page. Identify the company name, the job title, and the job location.

Page text:
{page_text}

Respond with ONLY a JSON object, no markdown fences, no extra text:
{{"company": <string or null>, "title": <string or null>, "location": <string or null>}}
"""

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class JobInfoExtractionError(RuntimeError):
    pass


class GeminiJobInfoExtractor:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.timeout = timeout
        if not self.api_key:
            raise JobInfoExtractionError("GEMINI_API_KEY is not set")
        if not self.model:
            raise JobInfoExtractionError("GEMINI_MODEL is not set")

    def extract(self, page_text: str) -> ExtractedJobInfo:
        prompt = _PROMPT_TEMPLATE.format(page_text=page_text[:8000])
        body = self._generate(prompt)
        text = _response_text(body)
        parsed = _parse_json(text)
        return ExtractedJobInfo(
            company=parsed.get("company"),
            title=parsed.get("title"),
            location=parsed.get("location"),
            jd_text=page_text,
        )

    def _generate(self, prompt: str) -> dict:
        url = f"{_ENDPOINT.format(model=self.model)}?key={self.api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300] if hasattr(exc, "read") else ""
            raise JobInfoExtractionError(f"HTTP {exc.code}: {detail}") from exc


def _response_text(body: dict) -> str:
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise JobInfoExtractionError(f"unexpected Gemini response shape: {json.dumps(body)[:300]}") from exc


def _parse_json(text: str) -> dict:
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        raise JobInfoExtractionError(f"no JSON object found in Gemini response: {text[:300]}")
    return json.loads(match.group(0))
