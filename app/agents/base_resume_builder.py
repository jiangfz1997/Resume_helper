from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import MasterProfile, TailoredResumeDraft

_prompt_text = (Path(__file__).parent.parent / "prompts" / "base_resume_builder.txt").read_text(encoding="utf-8")


class OllamaBaseResumeBuilder:
    def __init__(self) -> None:
        model = get_model_factory().build("base_resume_builder")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

    async def build(self, profile: MasterProfile) -> TailoredResumeDraft:
        result = await self._chain.ainvoke({"profile_json": profile.model_dump_json()})
        return TailoredResumeDraft.model_validate(result)
