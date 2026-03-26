import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.interfaces.base import IProfileEnricher, IProfileParser
from app.models.data_models import ParsedProfileDraft

logger = logging.getLogger(__name__)


class _GraphState(TypedDict):
    raw_text: str
    draft: Optional[ParsedProfileDraft]


class ProfileParsePipeline:
    def __init__(self, parser: IProfileParser, enricher: IProfileEnricher) -> None:
        self._parser = parser
        self._enricher = enricher
        self._graph = self._build_graph()

    def _build_graph(self) -> object:
        graph: StateGraph = StateGraph(_GraphState)  # type: ignore[type-arg]
        graph.add_node("parse", self._parse_node)  # type: ignore[arg-type]
        graph.add_node("enrich", self._enrich_node)  # type: ignore[arg-type]
        graph.set_entry_point("parse")
        graph.add_edge("parse", "enrich")
        graph.add_edge("enrich", END)
        return graph.compile()

    async def _parse_node(self, state: _GraphState) -> dict:
        logger.debug("node:parse | raw_text_len=%d", len(state["raw_text"]))
        draft = await self._parser.parse(state["raw_text"])
        logger.debug(
            "node:parse | done | experiences=%d education=%d projects=%d skills=%d",
            len(draft.work_experiences), len(draft.educations),
            len(draft.projects), len(draft.skills),
        )
        return {"draft": draft}

    async def _enrich_node(self, state: _GraphState) -> dict:
        draft: ParsedProfileDraft = state["draft"]
        logger.debug("node:enrich | skills_before=%d", len(draft.skills))
        enriched = await self._enricher.enrich(draft)
        logger.debug(
            "node:enrich | done | skills_after=%d experiences=%d",
            len(enriched.skills), len(enriched.work_experiences),
        )
        return {"draft": enriched}

    async def run(self, raw_text: str) -> ParsedProfileDraft:
        if not raw_text.strip():
            raise ValueError("PDF text is empty")
        initial_state: _GraphState = {"raw_text": raw_text, "draft": None}
        from app.pipeline._studio import _invoke
        final_state = await _invoke("profile_parse", self._graph, initial_state)
        draft: Optional[ParsedProfileDraft] = final_state["draft"]
        if draft is None:
            raise ValueError("Profile parsing pipeline failed to produce a result")
        return draft
