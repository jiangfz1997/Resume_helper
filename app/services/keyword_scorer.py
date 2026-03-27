import re
from functools import lru_cache

from pydantic import BaseModel

from app.models.data_models import JobDescription, MasterProfile, TailoredResumeDraft

# Weight per category — required keywords penalise more when missing
_CATEGORY_WEIGHT: dict[str, float] = {
    "hard_requirements": 1.0,
    "core_keywords": 0.8,
    "preferred_qualifications": 0.5,
    "soft_skills": 0.2,
}


class CategoryMatchResult(BaseModel):
    total: int
    matched: int
    missing: list[str]


class KeywordMatchResult(BaseModel):
    # Weighted composite score (0–1)
    score: float
    # Per-category breakdown
    hard_requirements: CategoryMatchResult
    core_keywords: CategoryMatchResult
    preferred_qualifications: CategoryMatchResult
    soft_skills: CategoryMatchResult
    # Flat lists for logging / display
    matched_keywords: list[str]
    missing_keywords: list[str]


def _keyword_in_text(keyword: str, text: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
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
    for proj in profile.projects:
        parts.append(proj.description)
        parts.extend(proj.bullets)
        parts.extend(proj.tech_stack)
    for skill in profile.skills:
        parts.append(skill.name)
    return " ".join(parts)


class KeywordScorer:
    def _score_from_text(self, text: str, jd: JobDescription) -> KeywordMatchResult:
        categories = {
            "hard_requirements": _dedup(jd.hard_requirements),
            "core_keywords": _dedup(jd.core_keywords),
            "preferred_qualifications": _dedup(jd.preferred_qualifications),
            "soft_skills": _dedup(jd.soft_skills),
        }

        results = {name: _match_category(kws, text) for name, kws in categories.items()}

        weighted_score = 0.0
        weight_sum = 0.0
        all_matched: list[str] = []
        all_missing: list[str] = []

        for name, cat in results.items():
            if cat.total == 0:
                continue
            w = _CATEGORY_WEIGHT[name]
            weighted_score += w * (cat.matched / cat.total)
            weight_sum += w
            matched_in_cat = [kw for kw in categories[name] if kw not in cat.missing]
            all_matched.extend(matched_in_cat)
            all_missing.extend(cat.missing)

        final_score = round(weighted_score / weight_sum, 4) if weight_sum > 0 else 0.0

        return KeywordMatchResult(
            score=final_score,
            hard_requirements=results["hard_requirements"],
            core_keywords=results["core_keywords"],
            preferred_qualifications=results["preferred_qualifications"],
            soft_skills=results["soft_skills"],
            matched_keywords=all_matched,
            missing_keywords=all_missing,
        )

    def score(self, draft: TailoredResumeDraft, jd: JobDescription) -> KeywordMatchResult:
        text = _extract_text_cached(draft.model_dump_json())
        return self._score_from_text(text, jd)

    def score_profile(self, profile: MasterProfile, jd: JobDescription) -> KeywordMatchResult:
        text = _extract_profile_text(profile)
        return self._score_from_text(text, jd)
