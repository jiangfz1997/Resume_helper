from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IResumeAuditor
from app.models.data_models import AuditFeedback, DraftResume, JobDescription

_prompt_text = (Path(__file__).parent.parent / "prompts" / "resume_auditor.txt").read_text(encoding="utf-8")


class OllamaResumeAuditor(IResumeAuditor):
    def __init__(self) -> None:
        model = get_model_factory().build("resume_auditor")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

    async def audit(self, draft: DraftResume, jd: JobDescription, threshold: float) -> AuditFeedback:
        result = await self._chain.ainvoke(
            {
                "jd_json": jd.model_dump_json(indent=2),
                "latex_content": draft.latex_content,
                "threshold": threshold,
            }
        )
        feedback = AuditFeedback.model_validate(result)
        feedback.approved = feedback.score >= threshold
        return feedback
