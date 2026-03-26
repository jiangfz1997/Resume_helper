import re
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IResumeGenerator
from app.models.data_models import (
    AuditFeedback,
    DraftResume,
    JobDescription,
    MasterProfile,
    MatchingReport,
)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_prompt_default = (_PROMPTS_DIR / "resume_generator.txt").read_text(encoding="utf-8")
_prompt_template = (_PROMPTS_DIR / "resume_generator_template.txt").read_text(encoding="utf-8")


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


_FEEDBACK_SECTION_TEMPLATE = """Previous Audit Feedback (iteration {iteration}):
Score: {score}
Suggestions:
{suggestions}

Address the suggestions above in this revised version.
"""


def _make_chain(prompt_text: str) -> object:
    model = get_model_factory().build("resume_generator")
    return ChatPromptTemplate.from_template(prompt_text) | model | StrOutputParser()


class OllamaResumeGenerator(IResumeGenerator):
    def __init__(self) -> None:
        self._chain_default = _make_chain(_prompt_default)
        self._chain_template = _make_chain(_prompt_template)

    async def generate(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        feedback: AuditFeedback | None,
        iteration: int,
        preamble: str | None = None,
        body_example: str | None = None,
    ) -> DraftResume:
        audit_feedback_section = ""
        if feedback is not None:
            suggestions_text = "\n".join(f"- {s}" for s in feedback.suggestions)
            audit_feedback_section = _FEEDBACK_SECTION_TEMPLATE.format(
                iteration=iteration,
                score=feedback.score,
                suggestions=suggestions_text,
            )

        if preamble and body_example:
            latex_content = await self._chain_template.ainvoke(
                {
                    "profile_json": profile.model_dump_json(indent=2),
                    "jd_json": jd.model_dump_json(indent=2),
                    "preamble": preamble,
                    "body_example": body_example,
                    "audit_feedback_section": audit_feedback_section,
                }
            )
        else:
            latex_content = await self._chain_default.ainvoke(
                {
                    "profile_json": profile.model_dump_json(indent=2),
                    "jd_json": jd.model_dump_json(indent=2),
                    "matching_report_json": matching_report.model_dump_json(indent=2),
                    "audit_feedback_section": audit_feedback_section,
                    "preamble_section": "",
                }
            )

        return DraftResume(latex_content=_strip_fences(latex_content), iteration=iteration)
