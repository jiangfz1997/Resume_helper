import re
from functools import lru_cache

from langsmith import traceable

from app.models.data_models import (
    CategoryMatchResult,
    JobDescription,
    KeywordMatchResult,
    MasterProfile,
    TailoredResumeDraft,
)

_KW_WEIGHT: dict[str, float] = {
    "tech_required": 1.0,
    "tech_preferred": 0.6,
    "nice_to_have": 0.2,
}


def _keyword_in_text(keyword: str, text: str) -> bool:
    escaped = re.escape(keyword)
    # \b doesn't work for keywords ending in non-word chars (C++, C#, .NET)
    # Use lookahead/lookbehind with \W or start/end of string instead
    pattern = re.compile(
        rf"(?<!\w){escaped}(?!\w)",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


@lru_cache(maxsize=256)
def _extract_text_cached(draft_json: str) -> str:
    import json

    data = json.loads(draft_json)
    parts: list[str] = []

    if data.get("summary"):
        parts.append(data["summary"])

    for exp in data.get("experiences", []):
        parts.append(exp.get("title", ""))
        for b in exp.get("bullets", []):
            parts.append(b.get("text", ""))

    for proj in data.get("projects", []):
        parts.append(proj.get("description", ""))
        for b in proj.get("bullets", []):
            parts.append(b.get("text", ""))

    for skill in data.get("skills", []):
        parts.append(skill.get("name", ""))

    return " ".join(parts)


def _dedup(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            result.append(kw)
    return result


def _match_category(keywords: list[str], text: str) -> CategoryMatchResult:
    missing: list[str] = []
    for kw in keywords:
        if not _keyword_in_text(kw, text):
            missing.append(kw)
    return CategoryMatchResult(
        total=len(keywords),
        matched=len(keywords) - len(missing),
        missing=missing,
    )


def _extract_profile_text(profile: MasterProfile) -> str:
    parts: list[str] = []
    if profile.summary:
        parts.append(profile.summary)
    for exp in profile.work_experiences:
        parts.append(exp.title)
        parts.extend(exp.description)
        parts.extend(exp.ai_keywords)
    for proj in profile.projects:
        parts.append(proj.description)
        parts.extend(proj.bullets)
        parts.extend(proj.tech_stack)
        parts.extend(proj.ai_keywords)
    for skill in profile.skills:
        parts.append(skill.name)
    return " ".join(parts)


def _build_result(text: str, jd: JobDescription) -> KeywordMatchResult:
    kw_categories = {
        "tech_required": _dedup(jd.tech_required),
        "tech_preferred": _dedup(jd.tech_preferred),
        "nice_to_have": _dedup(jd.nice_to_have),
    }

    kw_results = {name: _match_category(kws, text) for name, kws in kw_categories.items()}

    weighted_score = 0.0
    weight_sum = 0.0
    all_matched: list[str] = []
    all_missing: list[str] = []

    for name, cat in kw_results.items():
        if cat.total == 0:
            continue
        w = _KW_WEIGHT[name]
        weighted_score += w * (cat.matched / cat.total)
        weight_sum += w
        matched_in_cat = [kw for kw in kw_categories[name] if kw not in cat.missing]
        all_matched.extend(matched_in_cat)
        all_missing.extend(cat.missing)

    final_score = round(weighted_score / weight_sum, 4) if weight_sum > 0 else 0.0

    return KeywordMatchResult(
        score=final_score,
        tech_required=kw_results["tech_required"],
        tech_preferred=kw_results["tech_preferred"],
        nice_to_have=kw_results["nice_to_have"],
        matched_keywords=all_matched,
        missing_keywords=all_missing,
    )


class KeywordScorer:
    def score(self, draft: TailoredResumeDraft, jd: JobDescription) -> KeywordMatchResult:
        text = _extract_text_cached(draft.model_dump_json())
        return _build_result(text, jd)

    @traceable(run_type="tool", name="keyword_scorer")
    def score_profile(self, profile: MasterProfile, jd: JobDescription) -> KeywordMatchResult:
        text = _extract_profile_text(profile)
        return _build_result(text, jd)
