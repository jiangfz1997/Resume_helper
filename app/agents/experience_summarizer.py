import asyncio
import json
import logging
from pathlib import Path

from app.core.model_factory import get_model_factory
from app.interfaces.base import IExperienceSummarizer
from app.models.data_models import ParsedProfileDraft, Project, WorkExperience

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "experience_summarizer.txt").read_text(encoding="utf-8")


def _item_json(item: WorkExperience | Project) -> str:
    if isinstance(item, WorkExperience):
        return json.dumps({
            "type": "experience",
            "title": item.title,
            "company": item.company,
            "start_date": item.start_date,
            "end_date": item.end_date,
            "bullets": item.description,
        })
    return json.dumps({
        "type": "project",
        "name": item.name,
        "description": item.description,
        "tech_stack": item.tech_stack,
        "bullets": item.bullets,
    })


class ExperienceSummarizer(IExperienceSummarizer):
    def __init__(self) -> None:
        self._model = get_model_factory().build("experience_summarizer")

    async def _summarize_one(self, item: WorkExperience | Project) -> tuple[str, list[str]]:
        prompt = _prompt_text.replace("{item_json}", _item_json(item))
        try:
            response = await self._model.ainvoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            if isinstance(raw, list):
                text = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw
                )
            else:
                text = str(raw)
            data = json.loads(text)
            return str(data.get("summary", "")), [str(k) for k in data.get("keywords", [])]
        except Exception as exc:
            label = item.title if isinstance(item, WorkExperience) else item.name
            logger.warning("experience_summarizer | failed for %r: %s", label, exc)
            return "", []

    async def summarize(self, draft: ParsedProfileDraft) -> ParsedProfileDraft:
        all_items: list[WorkExperience | Project] = list(draft.work_experiences) + list(draft.projects)
        if not all_items:
            return draft

        results = await asyncio.gather(*[self._summarize_one(item) for item in all_items])

        n_exp = len(draft.work_experiences)
        updated_exp: list[WorkExperience] = []
        for i, exp in enumerate(draft.work_experiences):
            summary, keywords = results[i]
            updated_exp.append(exp.model_copy(update={"ai_summary": summary or None, "ai_keywords": keywords}))

        updated_proj: list[Project] = []
        for j, proj in enumerate(draft.projects):
            summary, keywords = results[n_exp + j]
            updated_proj.append(proj.model_copy(update={"ai_summary": summary or None, "ai_keywords": keywords}))

        logger.info(
            "experience_summarizer | done | exp=%d proj=%d",
            len(updated_exp), len(updated_proj),
        )
        return draft.model_copy(update={"work_experiences": updated_exp, "projects": updated_proj})
