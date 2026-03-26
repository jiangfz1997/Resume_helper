from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import JobDescription, MatchingReport, TailoredResumeDraft

_prompt_text = (Path(__file__).parent.parent / "prompts" / "resume_tailor.txt").read_text(encoding="utf-8")


class OllamaResumeTailor:
    def __init__(self) -> None:
        model = get_model_factory().build("resume_tailor")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

    async def tailor(
        self,
        base_resume: TailoredResumeDraft,
        jd: JobDescription,
        matching_report: MatchingReport,
    ) -> TailoredResumeDraft:
        result = await self._chain.ainvoke({
            "base_resume_json": base_resume.model_dump_json(),
            "jd_json": jd.model_dump_json(),
            "matching_report_json": matching_report.model_dump_json(),
        })
        return TailoredResumeDraft.model_validate(result)
