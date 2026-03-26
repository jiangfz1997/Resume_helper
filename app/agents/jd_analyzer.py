from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IJDAnalyzer
from app.models.data_models import JobDescription

_prompt_text = (Path(__file__).parent.parent / "prompts" / "jd_analyzer.txt").read_text(encoding="utf-8")


class OllamaJDAnalyzer(IJDAnalyzer):
    def __init__(self) -> None:
        model = get_model_factory().build("jd_analyzer")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

    async def analyze(self, jd_text: str) -> JobDescription:
        result = await self._chain.ainvoke({"jd_text": jd_text})
        return JobDescription.model_validate(result)
