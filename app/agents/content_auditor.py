import logging
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IContentAuditor
from app.models.data_models import AuditFeedback, JobDescription, TailoredResumeDraft

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "content_auditor.txt").read_text(
    encoding="utf-8"
)


class OllamaContentAuditor(IContentAuditor):
    def __init__(self) -> None:
        model = get_model_factory().build("content_auditor")
        self._chain = ChatPromptTemplate.from_template(_prompt_text) | model | JsonOutputParser()

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
        logger.debug(
            "content_auditor | score=%.2f approved=%s suggestions=%d",
            feedback.score, feedback.approved, len(feedback.suggestions),
        )
        return feedback
