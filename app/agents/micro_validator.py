import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import MicroValidateRequest, MicroValidateResponse

logger = logging.getLogger(__name__)

_prompt_text = (
    Path(__file__).parent.parent / "prompts" / "micro_validator.txt"
).read_text(encoding="utf-8")


class MicroValidator:
    def __init__(self) -> None:
        model = get_model_factory().build("micro_validator")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | StrOutputParser()

    async def validate(self, request: MicroValidateRequest) -> MicroValidateResponse:
        raw = await self._chain.ainvoke({
            "text": request.text,
            "condition": request.condition,
        })
        logger.debug("micro_validator | raw=%.200s", raw)

        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
            return MicroValidateResponse(
                passed=bool(data.get("passed", False)),
                reasoning=str(data.get("reasoning", "")),
            )
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("micro_validator | parse error: %s | raw=%.200s", exc, raw)
            return MicroValidateResponse(passed=False, reasoning="Could not parse model response.")
