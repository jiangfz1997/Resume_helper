import logging
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IContentAuditor
from app.models.data_models import AuditFeedback, JobDescription, TailoredResumeDraft
from app.services.keyword_scorer import KeywordScorer

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "content_auditor.txt").read_text(
    encoding="utf-8"
)


class OllamaContentAuditor(IContentAuditor):
    def __init__(self) -> None:
        model = get_model_factory().build("content_auditor")
        self._chain = ChatPromptTemplate.from_template(_prompt_text) | model | JsonOutputParser()
        self._scorer = KeywordScorer()

    async def audit(
        self,
        draft: TailoredResumeDraft,
        jd: JobDescription,
        threshold: float,
    ) -> AuditFeedback:
        result = await self._chain.ainvoke(
            {
                "jd_json": jd.model_dump_json(indent=2),
                "draft_json": draft.model_dump_json(indent=2),
                "threshold": threshold,
            }
        )
        feedback = AuditFeedback.model_validate(result)
        feedback.approved = feedback.score >= threshold
        kw_result = self._scorer.score(draft, jd)
        feedback.keyword_match_score = kw_result.score
        req = kw_result.hard_requirements
        feedback.required_keyword_coverage = round(req.matched / req.total, 4) if req.total else 0.0
        logger.debug(
            "content_auditor | score=%.2f kw_weighted=%.2f required=%.2f(%d/%d) approved=%s",
            feedback.score, feedback.keyword_match_score,
            feedback.required_keyword_coverage, req.matched, req.total,
            feedback.approved,
        )
        return feedback
