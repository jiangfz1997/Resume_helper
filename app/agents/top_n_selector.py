import json
import logging
from pathlib import Path
from typing import Union

from pydantic import BaseModel

from app.core.date_utils import duration_months
from app.core.model_factory import get_model_factory
from app.interfaces.base import ITopNSelector
from app.models.data_models import (
    JobDescription,
    MasterProfile,
    Project,
    SelectionResult,
    WorkExperience,
)

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "top_n_selector.txt").read_text(encoding="utf-8")

_LLM_SELECTED_MULTIPLIER: float = 2.0
_LLM_UNSELECTED_MULTIPLIER: float = 0.5


class _SemanticSelection(BaseModel):
    selected_ids: list[str]


def _item_id(item_type: str, index: int) -> str:
    return f"{item_type}_{index}"


def _item_keyword_set(item: Union[WorkExperience, Project]) -> set[str]:
    """Precise set from ai_keywords + ai_implied_keywords. Used for O(1) lookup."""
    return {k.lower() for k in (item.ai_keywords + item.ai_implied_keywords)}


def _item_rich_text(item: Union[WorkExperience, Project]) -> str:
    """Concatenated lowercase text for substring matching of multi-word phrases."""
    if isinstance(item, WorkExperience):
        parts = [item.title, item.company] + item.description
    else:
        parts = [item.name, item.description] + item.bullets + item.tech_stack
    return " ".join(p for p in parts if p).lower()


_BASE_SCORE_MIN: float = 0.05
_BASE_SCORE_MAX: float = 0.20
_BASE_SCORE_FULL_MONTHS: float = 24.0
_PROJECT_BASE_SCORE: float = 0.05


def _base_score(item: Union[WorkExperience, Project]) -> float:
    """Duration-weighted base score to prevent overlap=0 items from being permanently excluded.

    WorkExperience: linearly scaled by duration, clamped to [0.05, 0.20].
      0 months → 0.05, 24+ months → 0.20.
    Project: fixed 0.05 (no reliable duration data).
    """
    if isinstance(item, Project):
        return _PROJECT_BASE_SCORE
    months = duration_months(item.start_date, item.end_date)
    ratio = min(months / _BASE_SCORE_FULL_MONTHS, 1.0)
    return _BASE_SCORE_MIN + ratio * (_BASE_SCORE_MAX - _BASE_SCORE_MIN)


def _hit(kw: str, kw_set: set[str], rich_text: str) -> bool:
    """True if keyword matches via set (single-word) or substring (multi-word phrase)."""
    kw_lower = kw.lower()
    return kw_lower in kw_set or kw_lower in rich_text


def _tiered_overlap(item: Union[WorkExperience, Project], jd: JobDescription) -> float:
    """
    Weighted hit rate across 3 JD tiers:
      tech_required  weight 1.0
      tech_preferred weight 0.6
      nice_to_have   weight 0.2
    """
    total_weight = (
        1.0 * len(jd.tech_required) +
        0.6 * len(jd.tech_preferred) +
        0.2 * len(jd.nice_to_have)
    )
    if total_weight == 0:
        return 0.0

    kw_set = _item_keyword_set(item)
    rich_text = _item_rich_text(item)

    hit_weight = 0.0
    for kw in jd.tech_required:
        if _hit(kw, kw_set, rich_text):
            hit_weight += 1.0
    for kw in jd.tech_preferred:
        if _hit(kw, kw_set, rich_text):
            hit_weight += 0.6
    for kw in jd.nice_to_have:
        if _hit(kw, kw_set, rich_text):
            hit_weight += 0.2
    return hit_weight / total_weight


def _item_summary(item: Union[WorkExperience, Project]) -> str:
    if item.ai_summary:
        return item.ai_summary
    if isinstance(item, WorkExperience):
        return item.description[0] if item.description else f"{item.title} at {item.company}"
    return item.description or item.name


def _build_items_json(profile: MasterProfile) -> str:
    items = []
    for i, exp in enumerate(profile.work_experiences):
        items.append({
            "id": _item_id("exp", i),
            "type": "experience",
            "title": exp.title,
            "company": exp.company,
            "start_date": exp.start_date,
            "end_date": exp.end_date or "present",
            "summary": _item_summary(exp),
            "keywords": exp.ai_keywords,
        })
    for j, proj in enumerate(profile.projects):
        items.append({
            "id": _item_id("proj", j),
            "type": "project",
            "name": proj.name,
            "summary": _item_summary(proj),
            "keywords": proj.ai_keywords,
        })
    return json.dumps(items, ensure_ascii=False)


def _compute_overlap_scores(
    profile: MasterProfile,
    jd: JobDescription,
) -> tuple[list[float], list[float]]:
    exp_scores = [_tiered_overlap(e, jd) for e in profile.work_experiences]
    proj_scores = [_tiered_overlap(p, jd) for p in profile.projects]
    return exp_scores, proj_scores


def _log_overlap_scores(
    profile: MasterProfile,
    exp_scores: list[float],
    proj_scores: list[float],
    jd: JobDescription,
) -> None:
    lines = [f"=== TopNSelector | JD: {jd.title} @ {jd.company} ==="]
    lines.append(f"    tech_required={jd.tech_required}")
    lines.append(f"    tech_preferred={jd.tech_preferred}")
    lines.append(f"    nice_to_have={jd.nice_to_have}")
    lines.append("--- Track A: Tiered Overlap Scores ---")
    for i, (exp, score) in enumerate(zip(profile.work_experiences, exp_scores)):
        kw_set = _item_keyword_set(exp)
        lines.append(
            f"  exp_{i:<2} | {exp.title:<35} @ {exp.company:<20} | overlap={score:.3f}"
            f" | explicit={exp.ai_keywords} | implied={exp.ai_implied_keywords}"
            f" | signals={len(kw_set)}"
        )
    for j, (proj, score) in enumerate(zip(profile.projects, proj_scores)):
        kw_set = _item_keyword_set(proj)
        lines.append(
            f"  proj_{j:<1} | {proj.name:<55} | overlap={score:.3f}"
            f" | explicit={proj.ai_keywords} | implied={proj.ai_implied_keywords}"
            f" | signals={len(kw_set)}"
        )
    logger.debug("\n".join(lines))


def _log_fusion_result(
    profile: MasterProfile,
    exp_scores: list[float],
    proj_scores: list[float],
    llm_selected_ids: set[str],
    final_exp: list[int],
    final_proj: list[int],
) -> None:
    final_exp_set, final_proj_set = set(final_exp), set(final_proj)

    all_items: list[tuple[str, int, str, float]] = []
    for i, (exp, score) in enumerate(zip(profile.work_experiences, exp_scores)):
        label = f"{exp.title} @ {exp.company}"
        all_items.append((_item_id("exp", i), i, label, score))
    for j, (proj, score) in enumerate(zip(profile.projects, proj_scores)):
        all_items.append((_item_id("proj", j), j, proj.name, score))

    lines = ["--- Track B: LLM Semantic Selection ---"]
    if llm_selected_ids:
        lines.append(f"  selected_ids: {sorted(llm_selected_ids)}")
    else:
        lines.append("  (LLM unavailable — overlap-only fallback)")

    lines.append(
        f"--- Fusion (overlap * {_LLM_SELECTED_MULTIPLIER} if LLM selected, "
        f"* {_LLM_UNSELECTED_MULTIPLIER} otherwise) ---"
    )
    scored_rows = []
    for item_id, idx, label, overlap in all_items:
        typ = "exp" if item_id.startswith("exp") else "proj"
        m = _LLM_SELECTED_MULTIPLIER if item_id in llm_selected_ids else _LLM_UNSELECTED_MULTIPLIER
        final = overlap * m
        selected = (typ == "exp" and idx in final_exp_set) or (typ == "proj" and idx in final_proj_set)
        scored_rows.append((item_id, label, overlap, m, final, selected))

    scored_rows.sort(key=lambda x: x[4], reverse=True)
    for item_id, label, overlap, m, final, selected in scored_rows:
        marker = " <-- SELECTED" if selected else ""
        lines.append(
            f"  {item_id:<8} | {label:<50} | {overlap:.3f} * {m:.1f} = {final:.3f}{marker}"
        )
    lines.append(f"--- Final: exp={final_exp} proj={final_proj} ---")
    logger.debug("\n".join(lines))


def _fuse_and_select(
    exp_scores: list[float],
    proj_scores: list[float],
    profile_items_exp: list[WorkExperience],
    profile_items_proj: list[Project],
    llm_selected_ids: set[str],
    total_budget: int,
    min_exp: int,
    min_proj: int,
) -> tuple[list[int], list[int]]:
    scored: list[tuple[str, int, float]] = []
    for i, (exp, score) in enumerate(zip(profile_items_exp, exp_scores)):
        base = _base_score(exp)
        m = _LLM_SELECTED_MULTIPLIER if _item_id("exp", i) in llm_selected_ids else _LLM_UNSELECTED_MULTIPLIER
        scored.append(("exp", i, (score + base) * m))
    for j, (proj, score) in enumerate(zip(profile_items_proj, proj_scores)):
        base = _base_score(proj)
        m = _LLM_SELECTED_MULTIPLIER if _item_id("proj", j) in llm_selected_ids else _LLM_UNSELECTED_MULTIPLIER
        scored.append(("proj", j, (score + base) * m))

    scored.sort(key=lambda x: x[2], reverse=True)

    exp_indices: list[int] = []
    proj_indices: list[int] = []
    for typ, idx, _ in scored[:total_budget]:
        if typ == "exp":
            exp_indices.append(idx)
        else:
            proj_indices.append(idx)

    exp_indices, proj_indices = _enforce_minimums(
        exp_indices, proj_indices, scored, min_exp, min_proj, total_budget,
    )
    return exp_indices, proj_indices


def _enforce_minimums(
    exp_indices: list[int],
    proj_indices: list[int],
    scored: list[tuple[str, int, float]],
    min_exp: int,
    min_proj: int,
    total_budget: int,
) -> tuple[list[int], list[int]]:
    exp_set, proj_set = set(exp_indices), set(proj_indices)

    def _backfill(
        current: list[int],
        current_set: set[int],
        other: list[int],
        other_set: set[int],
        need_type: str,
        min_count: int,
    ) -> tuple[list[int], list[int]]:
        while len(current) < min_count:
            candidate = next(
                (idx for t, idx, _ in scored if t == need_type and idx not in current_set),
                None,
            )
            if candidate is None:
                break
            current.append(candidate)
            current_set.add(candidate)
            if len(current) + len(other) > total_budget and other:
                removed = other.pop()
                other_set.discard(removed)
        return current, other

    exp_indices, proj_indices = _backfill(exp_indices, exp_set, proj_indices, proj_set, "exp", min_exp)
    proj_indices, exp_indices = _backfill(proj_indices, proj_set, exp_indices, exp_set, "proj", min_proj)
    return exp_indices, proj_indices


class TopNSelector(ITopNSelector):
    def __init__(self) -> None:
        self._model = get_model_factory().build_chat_model("top_n_selector")
        self._structured = self._model.with_structured_output(_SemanticSelection)

    async def select(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        total_budget: int = 6,
        min_exp: int = 1,
        min_proj: int = 1,
    ) -> SelectionResult:
        n_exp = len(profile.work_experiences)
        n_proj = len(profile.projects)

        if n_exp + n_proj <= total_budget:
            logger.debug("top_n_selector | skipping — total items within budget")
            return SelectionResult(
                selected_experience_indices=list(range(n_exp)),
                selected_project_indices=list(range(n_proj)),
            )

        actual_min_exp = min(min_exp, n_exp)
        actual_min_proj = min(min_proj, n_proj)
        actual_budget = min(total_budget, n_exp + n_proj)

        exp_scores, proj_scores = _compute_overlap_scores(profile, jd)
        _log_overlap_scores(profile, exp_scores, proj_scores, jd)

        items_json = _build_items_json(profile)
        prompt = (
            _prompt_text
            .replace("{jd_json}", jd.model_dump_json())
            .replace("{items_json}", items_json)
            .replace("{max_select}", str(actual_budget))
        )

        llm_selected_ids: set[str] = set()
        try:
            result: _SemanticSelection = await self._structured.ainvoke(prompt)
            llm_selected_ids = set(result.selected_ids)
        except Exception as exc:
            logger.warning("top_n_selector | LLM failed (%s), using overlap scores only", exc)

        exp_indices, proj_indices = _fuse_and_select(
            exp_scores, proj_scores,
            profile.work_experiences, profile.projects,
            llm_selected_ids,
            actual_budget, actual_min_exp, actual_min_proj,
        )

        _log_fusion_result(profile, exp_scores, proj_scores, llm_selected_ids, exp_indices, proj_indices)

        logger.info(
            "top_n_selector | exp=%s proj=%s (budget=%d from %d/%d)",
            exp_indices, proj_indices, actual_budget, n_exp, n_proj,
        )
        return SelectionResult(
            selected_experience_indices=exp_indices,
            selected_project_indices=proj_indices,
        )
