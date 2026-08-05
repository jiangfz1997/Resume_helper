"""Offline tests only -- no real Gemini call. GeminiCoarseScorer._generate is
monkeypatched so the full score() path is exercised without a network
dependency in the default suite. See scripts/live_probe_gemini.py for the
real-API check.
"""

from datetime import datetime
from uuid import uuid4

import pytest

from job_discovery.domain.models import EligibilityStatus, JobRecord, ScoringProfile, WorkplaceType
from job_discovery.scoring.gemini_scorer import GeminiCoarseScorer, GeminiScoringError, _extract_text, _parse_score_json

# Shape matches the documented Generative Language API generateContent response.
SAMPLE_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            '{"score": 8, "reasoning": "Strong skills overlap.", '
                            '"required_years_min": 2, "required_years_max": null, '
                            '"requirement_keywords": ["Python", "AWS"]}'
                        )
                    }
                ]
            }
        }
    ]
}

FENCED_RESPONSE = {
    "candidates": [
        {"content": {"parts": [{"text": '```json\n{"score": 6, "reasoning": "Partial match, missing cloud skills."}\n```'}]}}
    ]
}


def _job() -> JobRecord:
    now = datetime(2026, 8, 5)
    return JobRecord(
        job_id=uuid4(),
        canonical_title="Software Engineer",
        canonical_company="Acme",
        canonical_location="Toronto, ON",
        workplace_type=WorkplaceType.ONSITE,
        description="Python, AWS, distributed systems.",
        description_chars=32,
        eligibility_status=EligibilityStatus.ELIGIBLE,
        created_at=now,
        updated_at=now,
    )


def test_extract_text_from_documented_response_shape() -> None:
    text = _extract_text(SAMPLE_RESPONSE)
    assert "score" in text


def test_extract_text_raises_on_unexpected_shape() -> None:
    with pytest.raises(GeminiScoringError):
        _extract_text({"unexpected": "shape"})


def test_parse_score_json_plain() -> None:
    parsed = _parse_score_json('{"score": 7, "reasoning": "Good fit."}')
    assert parsed.score == 7
    assert parsed.reasoning == "Good fit."
    assert parsed.required_years_min is None
    assert parsed.requirement_keywords == []


def test_parse_score_json_handles_markdown_fence() -> None:
    parsed = _parse_score_json('```json\n{"score": 6, "reasoning": "ok"}\n```')
    assert parsed.score == 6


def test_parse_score_json_extracts_requirements() -> None:
    parsed = _parse_score_json(
        '{"score": 9, "reasoning": "ok", "required_years_min": 3, "required_years_max": 5, '
        '"requirement_keywords": ["Python", "AWS", "CKA"]}'
    )
    assert parsed.required_years_min == 3
    assert parsed.required_years_max == 5
    assert parsed.requirement_keywords == ["Python", "AWS", "CKA"]


def test_parse_score_json_rejects_out_of_range() -> None:
    with pytest.raises(GeminiScoringError):
        _parse_score_json('{"score": 11, "reasoning": "x"}')


def test_score_end_to_end_with_monkeypatched_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    scorer = GeminiCoarseScorer(api_key="fake-key", model="fake-model")
    monkeypatch.setattr(scorer, "_generate", lambda prompt: SAMPLE_RESPONSE)

    result = scorer.score(_job(), ScoringProfile(skills=["Python", "AWS"]))
    assert result.score == 8
    assert result.model == "fake-model"
    assert result.required_years_min == 2
    assert result.required_years_max is None
    assert result.requirement_keywords == ["Python", "AWS"]


def test_score_end_to_end_with_fenced_response(monkeypatch: pytest.MonkeyPatch) -> None:
    scorer = GeminiCoarseScorer(api_key="fake-key", model="fake-model")
    monkeypatch.setattr(scorer, "_generate", lambda prompt: FENCED_RESPONSE)

    result = scorer.score(_job(), ScoringProfile(skills=["Python"]))
    assert result.score == 6


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiScoringError):
        GeminiCoarseScorer(api_key=None, model="fake-model")


def test_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(GeminiScoringError):
        GeminiCoarseScorer(api_key="fake-key", model=None)
