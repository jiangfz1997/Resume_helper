import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import (
    BatchVerifyResponse,
    BatchVerifyResult,
    DiagnosticTask,
)

logger = logging.getLogger(__name__)

_prompt_text = (
    Path(__file__).parent.parent / "prompts" / "batch_verifier.txt"
).read_text(encoding="utf-8")


class BatchVerifier:
    def __init__(self) -> None:
        model = get_model_factory().build("batch_verifier")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | StrOutputParser()

    async def verify(
        self,
        changed_sections: dict[str, str],
        tasks: list[DiagnosticTask],
    ) -> BatchVerifyResponse:
        sections_text = "\n".join(
            f"[{path}]\n{content}" for path, content in changed_sections.items()
        )
        tasks_json = json.dumps(
            [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "verify_condition": t.verify_condition,
                    "section": t.section,
                }
                for t in tasks
            ],
            indent=2,
        )
        raw = await self._chain.ainvoke(
            {"changed_sections": sections_text, "tasks_json": tasks_json}
        )
        logger.debug("batch_verifier | raw=%.400s", raw)

        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
            resolved = [
                BatchVerifyResult(id=r["id"], reason=r.get("reason", ""))
                for r in data.get("resolved", [])
                if isinstance(r.get("id"), str)
            ]
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("batch_verifier | parse failed: %s", exc)
            resolved = []

        logger.info("batch_verifier | resolved=%d / %d tasks", len(resolved), len(tasks))
        return BatchVerifyResponse(resolved=resolved)
