import logging
import re
import uuid
from dataclasses import dataclass
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.interfaces.base import IJDAnalyzer, ISkillMatcher, ITopNSelector
from app.models.data_models import (
    JobDescription,
    KeywordMatchResult,
    MasterProfile,
    MatchingPreview,
    MatchingReport,
    ResumeAnalyzeRequest,
    SelectionResult,
    SkillGapSuggestion,
)
from langsmith import traceable

from app.core.date_utils import parse_ym
from app.services.keyword_scorer import KeywordScorer
from app.services.profile_manager import ProfileManager

logger = logging.getLogger(__name__)

_DEFAULT_TOTAL_BUDGET = 6
_DEFAULT_MIN_EXP = 1
_DEFAULT_MIN_PROJ = 1

_INTERN_KEYWORDS = {"intern", "internship", "co-op", "coop", "co op", "student"}


def _calc_ft_experience_years(experiences: list) -> float:
    total_days = 0
    for exp in experiences:
        title_lower = (exp.title or "").lower()
        if any(kw in title_lower for kw in _INTERN_KEYWORDS):
            continue
        try:
            start = parse_ym(exp.start_date or "")
            end = parse_ym(exp.end_date or "present")
            days = (end - start).days
            if days > 0:
                total_days += days
        except Exception:
            continue
    return round(total_days / 365.25, 2)


def _validate_qualification_years(
    report: MatchingReport,
    profile: MasterProfile,
) -> MatchingReport:
    actual_years = _calc_ft_experience_years(profile.work_experiences)
    corrected = []
    changed = False
    for q in report.qualification_details:
        m = re.search(r"(\d+)\+?\s*years?", q.item, re.IGNORECASE)
        if m and q.matched:
            required = int(m.group(1))
            if actual_years < required:
                corrected.append(q.model_copy(update={
                    "matched": False,
                    "reason": f"FT experience ~{actual_years:.1f} yrs (excl. internships), requires {required}+",
                }))
                changed = True
                logger.info(
                    "qualification_validator | overrode matched=True for %r | actual=%.1f required=%d",
                    q.item, actual_years, required,
                )
                continue
        corrected.append(q)
    if not changed:
        return report
    return report.model_copy(update={"qualification_details": corrected})


def _tech_req_score(report: MatchingReport, jd: JobDescription) -> float:
    if not jd.tech_required:
        return 1.0
    if report.tech_coverage:
        score = sum(
            (0.8 if item.matched_via == "implied" else 1.0)
            for item in report.tech_coverage
            if item.matched
        )
        return min(score / len(jd.tech_required), 1.0)
    req_set = {k.lower() for k in jd.tech_required}
    matched_set = {s.lower() for s in report.matched_skills}
    return len(req_set & matched_set) / len(req_set)


def _tech_pref_score(kw_result: KeywordMatchResult) -> float:
    cat = kw_result.tech_preferred
    return cat.matched / cat.total if cat.total > 0 else 1.0


def _nice_score(kw_result: KeywordMatchResult) -> float:
    cat = kw_result.nice_to_have
    return cat.matched / cat.total if cat.total > 0 else 1.0


@dataclass
class AnalysisResult:
    preview: MatchingPreview
    profile: MasterProfile
    jd: JobDescription
    matching_report: MatchingReport


class _GraphState(TypedDict):
    user_id: str
    jd_text: str
    profile: Optional[MasterProfile]
    jd: Optional[JobDescription]
    selection: Optional[SelectionResult]
    matching_report: Optional[MatchingReport]


class ResumePipeline:
    def __init__(
        self,
        profile_manager: ProfileManager,
        jd_analyzer: IJDAnalyzer,
        skill_matcher: ISkillMatcher,
        top_n_selector: ITopNSelector,
        total_budget: int = _DEFAULT_TOTAL_BUDGET,
        min_exp: int = _DEFAULT_MIN_EXP,
        min_proj: int = _DEFAULT_MIN_PROJ,
    ) -> None:
        self._profile_manager = profile_manager
        self._jd_analyzer = jd_analyzer
        self._skill_matcher = skill_matcher
        self._top_n_selector = top_n_selector
        self._total_budget = total_budget
        self._min_exp = min_exp
        self._min_proj = min_proj
        self._graph = self._build_graph()

    def _build_graph(self) -> object:
        graph: StateGraph = StateGraph(_GraphState)  # type: ignore[type-arg]
        graph.add_node("load_profile", self._load_profile_node)  # type: ignore[arg-type]
        graph.add_node("analyze_jd", self._analyze_jd_node)  # type: ignore[arg-type]
        graph.add_node("select_top_n", self._select_top_n_node)  # type: ignore[arg-type]
        graph.add_node("match_skills", self._match_skills_node)  # type: ignore[arg-type]
        graph.set_entry_point("load_profile")
        graph.add_edge("load_profile", "analyze_jd")
        graph.add_edge("analyze_jd", "select_top_n")
        graph.add_edge("select_top_n", "match_skills")
        graph.add_edge("match_skills", END)
        return graph.compile()

    async def _load_profile_node(self, state: _GraphState) -> dict:
        logger.debug("node:load_profile | user_id=%s", state["user_id"])
        profile = await self._profile_manager.load_master_profile(uuid.UUID(state["user_id"]))
        if profile is None:
            raise ValueError("User profile not found")
        logger.debug(
            "node:load_profile | done | skills=%d experiences=%d",
            len(profile.skills), len(profile.work_experiences),
        )
        return {"profile": profile}

    async def _analyze_jd_node(self, state: _GraphState) -> dict:
        logger.debug("node:analyze_jd | jd_text_len=%d", len(state["jd_text"]))
        jd = await self._jd_analyzer.analyze(state["jd_text"])
        logger.debug(
            "node:analyze_jd | done | title=%s hard_reqs=%d req=%d pref=%d",
            jd.title, len(jd.qualifications), len(jd.tech_required), len(jd.tech_preferred),
        )
        return {"jd": jd}

    async def _select_top_n_node(self, state: _GraphState) -> dict:
        profile: MasterProfile = state["profile"]
        jd: JobDescription = state["jd"]
        logger.debug(
            "node:select_top_n | exp=%d proj=%d budget=%d",
            len(profile.work_experiences), len(profile.projects), self._total_budget,
        )
        selection = await self._top_n_selector.select(
            profile, jd, self._total_budget, self._min_exp, self._min_proj,
        )
        logger.debug(
            "node:select_top_n | selected exp=%s proj=%s",
            selection.selected_experience_indices, selection.selected_project_indices,
        )
        return {"selection": selection}

    async def _match_skills_node(self, state: _GraphState) -> dict:
        profile: MasterProfile = state["profile"]
        jd: JobDescription = state["jd"]
        selection: SelectionResult = state["selection"]

        selected_exp = [profile.work_experiences[i] for i in selection.selected_experience_indices if i < len(profile.work_experiences)]
        selected_proj = [profile.projects[i] for i in selection.selected_project_indices if i < len(profile.projects)]
        filtered_profile = profile.model_copy(update={
            "work_experiences": selected_exp,
            "projects": selected_proj,
        })

        logger.debug(
            "node:match_skills | filtered profile: exp=%d proj=%d skills=%d",
            len(filtered_profile.work_experiences), len(filtered_profile.projects), len(filtered_profile.skills),
        )
        report = await self._skill_matcher.match(filtered_profile, jd)
        logger.debug(
            "node:match_skills | done | matched=%d missing=%d",
            len(report.matched_skills), len(report.missing_skills),
        )
        report = report.model_copy(update={
            "topn_experience_indices": selection.selected_experience_indices,
            "topn_project_indices": selection.selected_project_indices,
        })
        return {"matching_report": report}

    @staticmethod
    def _compute_skill_gaps(
        profile: MasterProfile,
        jd: JobDescription,
        selection: SelectionResult,
    ) -> list[SkillGapSuggestion]:
        selected_kw: set[str] = set()
        for i in selection.selected_experience_indices:
            if i < len(profile.work_experiences):
                for kw in profile.work_experiences[i].ai_keywords:
                    selected_kw.add(kw.lower())
        for j in selection.selected_project_indices:
            if j < len(profile.projects):
                for kw in profile.projects[j].ai_keywords:
                    selected_kw.add(kw.lower())

        exp_set = set(selection.selected_experience_indices)
        proj_set = set(selection.selected_project_indices)
        suggestions: list[SkillGapSuggestion] = []

        for kw in jd.tech_required + jd.tech_preferred:
            if kw.lower() in selected_kw:
                continue
            covered_by: list[str] = []
            for i, exp in enumerate(profile.work_experiences):
                if i not in exp_set and kw.lower() in [k.lower() for k in exp.ai_keywords]:
                    covered_by.append(f"{exp.title} @ {exp.company}")
            for j, proj in enumerate(profile.projects):
                if j not in proj_set and kw.lower() in [k.lower() for k in proj.ai_keywords]:
                    covered_by.append(proj.name)
            if covered_by:
                suggestions.append(SkillGapSuggestion(missing_keyword=kw, covered_by=covered_by))

        return suggestions

    @traceable(run_type="chain", name="analyze_and_preview")
    async def analyze_and_preview(
        self,
        user_id: uuid.UUID,
        request: ResumeAnalyzeRequest,
    ) -> AnalysisResult:
        initial_state: _GraphState = {
            "user_id": str(user_id),
            "jd_text": request.jd_text,
            "profile": None,
            "jd": None,
            "selection": None,
            "matching_report": None,
        }

        from app.pipeline._studio import _invoke
        final_state = await _invoke("resume_pipeline", self._graph, initial_state)

        profile: MasterProfile = final_state["profile"]
        jd: JobDescription = final_state["jd"]
        report: MatchingReport = _validate_qualification_years(final_state["matching_report"], profile)
        selection: SelectionResult = final_state["selection"]

        exp_indices = selection.selected_experience_indices
        proj_indices = selection.selected_project_indices

        filtered_profile = profile.model_copy(update={
            "work_experiences": [profile.work_experiences[i] for i in exp_indices if i < len(profile.work_experiences)],
            "projects": [profile.projects[j] for j in proj_indices if j < len(profile.projects)],
        })

        kw_result = KeywordScorer().score_profile(filtered_profile, jd)

        tech_req_score = _tech_req_score(report, jd)
        tech_pref_score = _tech_pref_score(kw_result)
        nice_score = _nice_score(kw_result)

        qual_details = report.qualification_details
        qual_score: Optional[float] = (
            sum(1 for q in qual_details if q.matched) / len(qual_details)
            if qual_details else None
        )

        if qual_score is not None:
            match_score = round(
                0.40 * tech_req_score
                + 0.35 * qual_score
                + 0.20 * tech_pref_score
                + 0.05 * nice_score,
                4,
            )
        else:
            match_score = round(
                0.55 * tech_req_score
                + 0.27 * tech_pref_score
                + 0.18 * nice_score,
                4,
            )

        gap_suggestions = self._compute_skill_gaps(profile, jd, selection)

        # remap skill_matcher's relative highlighted indices back to full-profile indices
        highlighted_exp = [
            exp_indices[i] for i in report.highlighted_experience_indices
            if i < len(exp_indices)
        ]
        highlighted_proj = [
            proj_indices[j] for j in report.highlighted_project_indices
            if j < len(proj_indices)
        ]

        preview = MatchingPreview(
            session_id="",
            match_score=match_score,
            job_title=jd.title,
            company=jd.company,
            matched_skills=report.matched_skills,
            missing_skills=report.missing_skills,
            highlighted_experience_indices=highlighted_exp,
            highlighted_project_indices=highlighted_proj,
            topn_experience_indices=exp_indices,
            topn_project_indices=proj_indices,
            all_experiences=profile.work_experiences,
            all_projects=profile.projects,
            relevance_notes=report.relevance_notes,
            qualification_details=report.qualification_details,
            kw_detail=kw_result,
            skill_gap_suggestions=gap_suggestions,
        )
        return AnalysisResult(preview=preview, profile=profile, jd=jd, matching_report=report)
