import json
import logging
from pathlib import Path
from typing import Union

from pydantic import BaseModel

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


def _keyword_overlap(item_keywords: list[str], jd_keywords: list[str]) -> float:
    if not jd_keywords:
        return 0.0
    jd_set = {k.lower() for k in jd_keywords}
    item_set = {k.lower() for k in item_keywords}
    return len(jd_set & item_set) / len(jd_set)


def _item_id(item_type: str, index: int) -> str:
    return f"{item_type}_{index}"


def _item_keywords(item: Union[WorkExperience, Project]) -> list[str]:
    if item.ai_keywords:
        return item.ai_keywords
    if isinstance(item, WorkExperience):
        return []
    return item.tech_stack


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
            "keywords": _item_keywords(exp),
        })
    for j, proj in enumerate(profile.projects):
        items.append({
            "id": _item_id("proj", j),
            "type": "project",
            "name": proj.name,
            "summary": _item_summary(proj),
            "keywords": _item_keywords(proj),
        })
    return json.dumps(items, ensure_ascii=False)


def _log_overlap_scores(
    profile: MasterProfile,
    exp_scores: list[float],
    proj_scores: list[float],
    jd: JobDescription,
) -> None:
    lines = [f"=== TopNSelector | JD: {jd.title} @ {jd.company} ==="]
    lines.append("--- Track A: Keyword Overlap Scores ---")
    for i, (exp, score) in enumerate(zip(profile.work_experiences, exp_scores)):
        kw = _item_keywords(exp)
        lines.append(
            f"  exp_{i:<2} | {exp.title:<35} @ {exp.company:<25} | overlap={score:.3f} | kw={kw}"
        )
    for j, (proj, score) in enumerate(zip(profile.projects, proj_scores)):
        kw = _item_keywords(proj)
        lines.append(
            f"  proj_{j:<1} | {proj.name:<60} | overlap={score:.3f} | kw={kw}"
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


def _compute_overlap_scores(
    profile: MasterProfile,
    jd: JobDescription,
) -> tuple[list[float], list[float]]:
    all_jd_kw = jd.tech_keywords + jd.preferred_qualifications
    exp_scores = [_keyword_overlap(_item_keywords(e), all_jd_kw) for e in profile.work_experiences]
    proj_scores = [_keyword_overlap(_item_keywords(p), all_jd_kw) for p in profile.projects]
    return exp_scores, proj_scores


def _fuse_and_select(
    exp_scores: list[float],
    proj_scores: list[float],
    llm_selected_ids: set[str],
    total_budget: int,
    min_exp: int,
    min_proj: int,
) -> tuple[list[int], list[int]]:
    scored: list[tuple[str, int, float]] = []
    for i, score in enumerate(exp_scores):
        m = _LLM_SELECTED_MULTIPLIER if _item_id("exp", i) in llm_selected_ids else _LLM_UNSELECTED_MULTIPLIER
        scored.append(("exp", i, score * m))
    for j, score in enumerate(proj_scores):
        m = _LLM_SELECTED_MULTIPLIER if _item_id("proj", j) in llm_selected_ids else _LLM_UNSELECTED_MULTIPLIER
        scored.append(("proj", j, score * m))

    scored.sort(key=lambda x: x[2], reverse=True)

    exp_indices: list[int] = []
    proj_indices: list[int] = []
    for typ, idx, _ in scored[:total_budget]:
        if typ == "exp":
            exp_indices.append(idx)
        else:
            proj_indices.append(idx)

    # enforce per-type minimums by swapping in top-scored items of the missing type
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
        other_type: str,
        min_count: int,
    ) -> tuple[list[int], list[int]]:
        while len(current) < min_count:
            # find highest-scored item of need_type not already selected
            candidate = next(
                (idx for t, idx, _ in scored if t == need_type and idx not in current_set),
                None,
            )
            if candidate is None:
                break
            current.append(candidate)
            current_set.add(candidate)
            # if over budget, drop the lowest-scored item from the other type
            if len(current) + len(other) > total_budget and other:
                removed = other.pop()
                other_set.discard(removed)
        return current, other

    exp_indices, proj_indices = _backfill(exp_indices, exp_set, proj_indices, proj_set, "exp", "proj", min_exp)
    proj_indices, exp_indices = _backfill(proj_indices, proj_set, exp_indices, exp_set, "proj", "exp", min_proj)
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
        max_select = actual_budget

        exp_scores, proj_scores = _compute_overlap_scores(profile, jd)

        items_json = _build_items_json(profile)
        prompt = (
            _prompt_text
            .replace("{jd_json}", jd.model_dump_json())
            .replace("{items_json}", items_json)
            .replace("{max_select}", str(max_select))
        )

        _log_overlap_scores(profile, exp_scores, proj_scores, jd)

        llm_selected_ids: set[str] = set()
        try:
            result: _SemanticSelection = await self._structured.ainvoke(prompt)
            llm_selected_ids = set(result.selected_ids)
        except Exception as exc:
            logger.warning("top_n_selector | LLM failed (%s), using overlap scores only", exc)

        exp_indices, proj_indices = _fuse_and_select(
            exp_scores, proj_scores, llm_selected_ids,
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
