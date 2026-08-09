"""Gemini-backed CoarseScorer. Plain HTTPS REST via stdlib urllib, no SDK
dependency -- consistent with the rest of this project's adapters (Workday,
jobspy) and keeps any Lambda that imports this thin.

Deliberately reimplemented rather than migrated from ApplyPilot's
scoring/scorer.py (AGPL-3.0-only): a structured ScoringProfile is sent, never
resume text -- both for the licensing boundary and because it cuts input
tokens by roughly an order of magnitude versus sending a full resume.

GEMINI_MODEL has no hardcoded default on purpose: free-tier model names on
the Generative Language API change over time, and guessing one risks a
silent 404 or a model that has since lost free-tier eligibility. Check
https://aistudio.google.com/ for the current name and set it explicitly.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from job_discovery.domain.models import CoarseScore, JobRecord, ScoringProfile

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT_TEMPLATE = """You are screening one job posting against a candidate profile for a quick relevance score. Do not evaluate anything except fit between the profile and the posting.

Candidate skills: {skills}
Candidate target titles: {target_titles}
Candidate minimum years of experience: {min_years}
Candidate location preference: {location_pref}
Candidate seniority preference: {seniority_pref}

Job title: {title}
Job company: {company}
Job location: {location}
Job description:
{description}

Score the match from 1 (poor) to 10 (excellent). Also extract, strictly from the job description text, the concrete requirement keywords (required skills, tools, certifications, degrees -- not soft skills or company perks). Respond with ONLY a JSON object, no markdown fences, no extra text:
{{"score": <integer 1-10>, "reasoning": "<two sentences max>", "requirement_keywords": [<string>, ...]}}
"""

_NEW_GRAD_PREFERENCE = (
    "entry-level or new-graduate roles. Score postings that expect substantial "
    "prior industry experience low even when the skills line up."
)
_NO_SENIORITY_PREFERENCE = "none stated"

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class GeminiScoringError(RuntimeError):
    pass


class _ParsedScore(BaseModel):
    score: int
    reasoning: str
    requirement_keywords: list[str] = Field(default_factory=list)


class GeminiCoarseScorer:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.timeout = timeout
        if not self.api_key:
            raise GeminiScoringError("GEMINI_API_KEY is not set")
        if not self.model:
            raise GeminiScoringError(
                "GEMINI_MODEL is not set -- check https://aistudio.google.com/ for the current free-tier model name"
            )

    def score(self, job: JobRecord, profile: ScoringProfile) -> CoarseScore:
        prompt = _PROMPT_TEMPLATE.format(
            skills=", ".join(profile.skills) or "unspecified",
            target_titles=", ".join(profile.target_titles) or "any",
            min_years=profile.min_years_experience if profile.min_years_experience is not None else "unspecified",
            location_pref=profile.location_preference or "unspecified",
            seniority_pref=_NEW_GRAD_PREFERENCE if profile.prefers_new_grad else _NO_SENIORITY_PREFERENCE,
            title=job.canonical_title,
            company=job.canonical_company,
            location=job.canonical_location or "unspecified",
            description=(job.description or "")[:6000],
        )
        body = self._generate(prompt)
        text = _extract_text(body)
        parsed = _parse_score_json(text)
        return CoarseScore(
            score=parsed.score,
            reasoning=parsed.reasoning,
            model=self.model,
            scored_at=datetime.now(timezone.utc),
            requirement_keywords=parsed.requirement_keywords,
        )

    def _generate(self, prompt: str) -> dict:
        url = f"{_ENDPOINT.format(model=self.model)}?key={self.api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300] if hasattr(exc, "read") else ""
            raise GeminiScoringError(f"HTTP {exc.code}: {detail}") from exc


def _extract_text(body: dict) -> str:
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiScoringError(f"unexpected Gemini response shape: {json.dumps(body)[:300]}") from exc


def _parse_score_json(text: str) -> _ParsedScore:
    """Handles plain JSON and markdown-fenced JSON alike -- the regex only
    looks for the outermost braces, ignoring any ```json fence around them."""
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        raise GeminiScoringError(f"no JSON object found in Gemini response: {text[:300]}")
    data = json.loads(match.group(0))
    score = int(data["score"])
    if not (1 <= score <= 10):
        raise GeminiScoringError(f"score out of range: {score}")
    keywords = data.get("requirement_keywords") or []
    return _ParsedScore(
        score=score,
        reasoning=str(data.get("reasoning", ""))[:500],
        requirement_keywords=[str(k) for k in keywords][:20],
    )
