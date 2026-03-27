import logging
import uuid
from dataclasses import dataclass
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.interfaces.base import IJDAnalyzer, IResumeAuditor, IResumeGenerator, ISkillMatcher
from app.models.data_models import (
    AuditFeedback,
    DraftResume,
    GenerateConfirmRequest,
    JobDescription,
    MasterProfile,
    MatchingPreview,
    MatchingReport,
    PipelineConfig,
    PipelineStatus,
    ResumeAnalyzeRequest,
    ResumeRequest,
    ResumeResponse,
)
from app.services.keyword_scorer import KeywordScorer
from app.services.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    preview: MatchingPreview
    profile: MasterProfile
    jd: JobDescription
    matching_report: MatchingReport


class _GraphState(TypedDict):
    user_id: str
    jd_text: str
    config: PipelineConfig
    preamble: Optional[str]
    body_example: Optional[str]
    profile: Optional[MasterProfile]
    jd: Optional[JobDescription]
    matching_report: Optional[MatchingReport]
    current_draft: Optional[DraftResume]
    feedback: Optional[AuditFeedback]
    best_draft: Optional[DraftResume]
    best_score: float
    retry_count: int
    current_threshold: float
    status: PipelineStatus


class ResumePipeline:
    def __init__(
        self,
        profile_manager: ProfileManager,
        jd_analyzer: IJDAnalyzer,
        skill_matcher: ISkillMatcher,
        resume_generator: IResumeGenerator,
        resume_auditor: IResumeAuditor,
    ) -> None:
        self._profile_manager = profile_manager
        self._jd_analyzer = jd_analyzer
        self._skill_matcher = skill_matcher
        self._resume_generator = resume_generator
        self._resume_auditor = resume_auditor
        self._analysis_graph = self._build_analysis_graph()
        self._generation_graph = self._build_generation_graph()

    def _build_analysis_graph(self) -> object:
        graph: StateGraph = StateGraph(_GraphState)  # type: ignore[type-arg]
        graph.add_node("load_profile", self._load_profile_node)  # type: ignore[arg-type]
        graph.add_node("analyze_jd", self._analyze_jd_node)  # type: ignore[arg-type]
        graph.add_node("match_skills", self._match_skills_node)  # type: ignore[arg-type]
        graph.set_entry_point("load_profile")
        graph.add_edge("load_profile", "analyze_jd")
        graph.add_edge("analyze_jd", "match_skills")
        graph.add_edge("match_skills", END)
        return graph.compile()

    def _build_generation_graph(self) -> object:
        graph: StateGraph = StateGraph(_GraphState)  # type: ignore[type-arg]
        graph.add_node("generate", self._generate_node)  # type: ignore[arg-type]
        graph.add_node("audit", self._audit_node)  # type: ignore[arg-type]
        graph.set_entry_point("generate")
        graph.add_edge("generate", "audit")
        graph.add_conditional_edges("audit", self._route_after_audit)  # type: ignore[arg-type]
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
            "node:analyze_jd | done | title=%s hard_reqs=%d keywords=%d",
            jd.title, len(jd.hard_requirements), len(jd.core_keywords),
        )
        return {"jd": jd}

    async def _match_skills_node(self, state: _GraphState) -> dict:
        logger.debug("node:match_skills | profile_skills=%d", len(state["profile"].skills))
        report = await self._skill_matcher.match(state["profile"], state["jd"])
        logger.debug(
            "node:match_skills | done | matched=%d missing=%d",
            len(report.matched_skills), len(report.missing_skills),
        )
        return {"matching_report": report}

    async def _generate_node(self, state: _GraphState) -> dict:
        logger.debug(
            "node:generate | iteration=%d feedback=%s",
            state["retry_count"], "yes" if state["feedback"] else "none",
        )
        draft = await self._resume_generator.generate(
            profile=state["profile"],
            jd=state["jd"],
            matching_report=state["matching_report"],
            feedback=state["feedback"],
            iteration=state["retry_count"],
            preamble=state.get("preamble"),
            body_example=state.get("body_example"),
        )
        logger.debug("node:generate | done | latex_len=%d", len(draft.latex_content))
        return {"current_draft": draft}

    async def _audit_node(self, state: _GraphState) -> dict:
        cfg: PipelineConfig = state["config"]
        logger.debug("node:audit | iteration=%d threshold=%.2f", state["retry_count"], state["current_threshold"])
        feedback = await self._resume_auditor.audit(
            state["current_draft"],
            state["jd"],
            state["current_threshold"],
        )
        logger.info(
            "node:audit | score=%.2f approved=%s suggestions=%d",
            feedback.score, feedback.approved, len(feedback.suggestions),
        )

        new_best_score = state["best_score"]
        new_best_draft = state["best_draft"]
        if feedback.score > state["best_score"]:
            new_best_score = feedback.score
            new_best_draft = state["current_draft"]

        new_retry_count = state["retry_count"] + 1

        if feedback.approved:
            new_status = PipelineStatus.approved
        elif new_retry_count >= cfg.max_retries:
            new_status = PipelineStatus.max_retries_reached
        else:
            new_status = PipelineStatus.in_progress

        new_threshold = max(
            cfg.min_threshold,
            state["current_threshold"] - cfg.decay_per_retry,
        )

        logger.debug("node:audit | next_status=%s next_threshold=%.2f", new_status, new_threshold)
        return {
            "feedback": feedback,
            "best_score": new_best_score,
            "best_draft": new_best_draft,
            "retry_count": new_retry_count,
            "current_threshold": new_threshold,
            "status": new_status,
        }

    def _route_after_audit(self, state: _GraphState) -> str:
        next_node = "generate" if state["status"] == PipelineStatus.in_progress else END
        logger.debug("node:route | -> %s", next_node)
        return next_node

    def _blank_state(self, user_id: str, jd_text: str, config: PipelineConfig) -> _GraphState:
        return {
            "user_id": user_id,
            "jd_text": jd_text,
            "config": config,
            "preamble": None,
            "body_example": None,
            "profile": None,
            "jd": None,
            "matching_report": None,
            "current_draft": None,
            "feedback": None,
            "best_draft": None,
            "best_score": 0.0,
            "retry_count": 0,
            "current_threshold": config.initial_threshold,
            "status": PipelineStatus.in_progress,
        }

    async def analyze_and_preview(
        self,
        user_id: uuid.UUID,
        request: ResumeAnalyzeRequest,
    ) -> AnalysisResult:
        default_cfg = PipelineConfig()
        initial_state = self._blank_state(str(user_id), request.jd_text, default_cfg)

        final_state = await self._analysis_graph.ainvoke(initial_state)

        profile: MasterProfile = final_state["profile"]
        jd: JobDescription = final_state["jd"]
        report: MatchingReport = final_state["matching_report"]

        total = len(report.matched_skills) + len(report.missing_skills)
        match_score = len(report.matched_skills) / total if total > 0 else 0.0

        kw_result = KeywordScorer().score_profile(profile, jd)
        req = kw_result.hard_requirements

        preview = MatchingPreview(
            session_id="",  # filled in by route after DB insert
            match_score=match_score,
            job_title=jd.title,
            company=jd.company,
            matched_skills=report.matched_skills,
            missing_skills=report.missing_skills,
            highlighted_experiences=report.highlighted_experiences,
            all_experiences=profile.work_experiences,
            all_projects=profile.projects,
            relevance_notes=report.relevance_notes,
            keyword_coverage=kw_result.score,
            required_coverage=round(req.matched / req.total, 4) if req.total else 0.0,
        )
        return AnalysisResult(preview=preview, profile=profile, jd=jd, matching_report=report)


    async def run(self, user_id: uuid.UUID, request: ResumeRequest) -> ResumeResponse:
        initial_state = self._blank_state(str(user_id), request.jd_text, request.config)
        full_graph = self._build_full_graph()
        final_state = await full_graph.ainvoke(initial_state)

        if final_state["best_draft"] is None:
            raise ValueError("Pipeline failed to produce a resume draft")

        return ResumeResponse(
            latex_content=final_state["best_draft"].latex_content,
            score=final_state["best_score"],
            retries=final_state["retry_count"],
            status=final_state["status"],
        )

    def _build_full_graph(self) -> object:
        graph: StateGraph = StateGraph(_GraphState)  # type: ignore[type-arg]
        graph.add_node("load_profile", self._load_profile_node)  # type: ignore[arg-type]
        graph.add_node("analyze_jd", self._analyze_jd_node)  # type: ignore[arg-type]
        graph.add_node("match_skills", self._match_skills_node)  # type: ignore[arg-type]
        graph.add_node("generate", self._generate_node)  # type: ignore[arg-type]
        graph.add_node("audit", self._audit_node)  # type: ignore[arg-type]
        graph.set_entry_point("load_profile")
        graph.add_edge("load_profile", "analyze_jd")
        graph.add_edge("analyze_jd", "match_skills")
        graph.add_edge("match_skills", "generate")
        graph.add_edge("generate", "audit")
        graph.add_conditional_edges("audit", self._route_after_audit)  # type: ignore[arg-type]
        return graph.compile()
