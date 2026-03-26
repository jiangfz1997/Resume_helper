import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.content_drafter import OllamaContentDrafter
from app.interfaces.base import IContentAuditor
from app.models.data_models import (
    AuditFeedback,
    JobDescription,
    MasterProfile,
    MatchingReport,
    PipelineConfig,
    PipelineStatus,
    TailoredResumeDraft,
)

logger = logging.getLogger(__name__)


def _v2_serialize(state: "_V2State") -> dict:
    return {
        "profile": state["profile"].model_dump(),
        "jd": state["jd"].model_dump(),
        "matching_report": state["matching_report"].model_dump(),
        "config": state["config"].model_dump(),
        "tailored_draft": None,
        "feedback": None,
        "best_tailored_draft": None,
        "best_score": 0.0,
        "retry_count": 0,
        "current_threshold": state["config"].initial_threshold,
        "status": PipelineStatus.in_progress.value,
    }


class _V2State(TypedDict):
    profile: MasterProfile
    jd: JobDescription
    matching_report: MatchingReport
    config: PipelineConfig
    tailored_draft: Optional[TailoredResumeDraft]
    feedback: Optional[AuditFeedback]
    best_tailored_draft: Optional[TailoredResumeDraft]
    best_score: float
    retry_count: int
    current_threshold: float
    status: PipelineStatus


class V2ResumePipeline:
    def __init__(
        self,
        drafter: OllamaContentDrafter,
        auditor: IContentAuditor,
    ) -> None:
        self._drafter = drafter
        self._auditor = auditor
        self._graph = self._build_graph()

    def _build_graph(self) -> object:
        graph: StateGraph = StateGraph(_V2State)  # type: ignore[type-arg]
        graph.add_node("draft", self._draft_node)  # type: ignore[arg-type]
        graph.add_node("audit", self._audit_node)  # type: ignore[arg-type]
        graph.set_entry_point("draft")
        graph.add_edge("draft", "audit")
        graph.add_conditional_edges("audit", self._route)  # type: ignore[arg-type]
        return graph.compile()

    async def _draft_node(self, state: _V2State) -> dict:
        logger.debug(
            "v2:draft | iteration=%d feedback=%s",
            state["retry_count"], "yes" if state["feedback"] else "none",
        )
        draft = await self._drafter.draft(
            profile=state["profile"],
            jd=state["jd"],
            matching_report=state["matching_report"],
            feedback=state["feedback"],
            iteration=state["retry_count"],
        )
        logger.debug("v2:draft | done | experiences=%d", len(draft.experiences))
        return {"tailored_draft": draft}

    async def _audit_node(self, state: _V2State) -> dict:
        cfg: PipelineConfig = state["config"]
        logger.debug(
            "v2:audit | iteration=%d threshold=%.2f", state["retry_count"], state["current_threshold"]
        )
        feedback = await self._auditor.audit(
            state["tailored_draft"], state["jd"], state["current_threshold"]
        )
        logger.info(
            "v2:audit | score=%.2f approved=%s suggestions=%d",
            feedback.score, feedback.approved, len(feedback.suggestions),
        )

        new_best_score = state["best_score"]
        new_best_draft = state["best_tailored_draft"]
        if feedback.score > state["best_score"]:
            new_best_score = feedback.score
            new_best_draft = state["tailored_draft"]

        new_retry = state["retry_count"] + 1

        if feedback.approved:
            new_status = PipelineStatus.approved
        elif new_retry >= cfg.max_retries:
            new_status = PipelineStatus.max_retries_reached
        else:
            new_status = PipelineStatus.in_progress

        new_threshold = max(cfg.min_threshold, state["current_threshold"] - cfg.decay_per_retry)

        return {
            "feedback": feedback,
            "best_tailored_draft": new_best_draft,
            "best_score": new_best_score,
            "retry_count": new_retry,
            "current_threshold": new_threshold,
            "status": new_status,
        }

    def _route(self, state: _V2State) -> str:
        nxt = "draft" if state["status"] == PipelineStatus.in_progress else END
        logger.debug("v2:route | -> %s", nxt)
        return nxt

    async def run(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        config: PipelineConfig,
        template_id=None,
        template_source=None,
    ) -> TailoredResumeDraft:
        initial: _V2State = {
            "profile": profile,
            "jd": jd,
            "matching_report": matching_report,
            "config": config,
            "tailored_draft": None,
            "feedback": None,
            "best_tailored_draft": None,
            "best_score": 0.0,
            "retry_count": 0,
            "current_threshold": config.initial_threshold,
            "status": PipelineStatus.in_progress,
        }

        from app.pipeline._studio import _invoke
        final = await _invoke("v2_resume", self._graph, _v2_serialize(initial))

        best: TailoredResumeDraft | None = final["best_tailored_draft"]
        if best is None:
            raise ValueError("V2 pipeline failed to produce a draft")

        return best.model_copy(update={
            "template_id": template_id,
            "template_source": template_source,
        })
