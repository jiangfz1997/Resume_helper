import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import ISkillMatcher
from app.models.data_models import JobDescription, MasterProfile, MatchingReport

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "skill_matcher.txt").read_text(encoding="utf-8")


def _build_profile_summary(profile: MasterProfile) -> str:
    skills = [f"{s.name} ({s.proficiency})" for s in profile.skills]
    exps = [
        f"{e.title} at {e.company} ({e.start_date}-{e.end_date or 'present'})"
        for e in profile.work_experiences
    ]
    projs = [f"{p.name}: {p.description}" for p in profile.projects]
    parts = []
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    if exps:
        parts.append("Experience:\n" + "\n".join(f"  - {x}" for x in exps))
    if projs:
        parts.append("Projects:\n" + "\n".join(f"  - {x}" for x in projs))
    return "\n".join(parts) if parts else "(empty profile)"


class OllamaSkillMatcher(ISkillMatcher):
    def __init__(self) -> None:
        model = get_model_factory().build("skill_matcher")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | StrOutputParser()

    async def match(self, profile: MasterProfile, jd: JobDescription) -> MatchingReport:
        invoke_input = {
            "profile_json": _build_profile_summary(profile),
            "jd_json": jd.model_dump_json(indent=2),
        }
        last_exc: Exception = ValueError("skill_matcher: no attempts made")
        for attempt in range(3):
            raw = await self._chain.ainvoke(invoke_input)
            logger.debug("skill_matcher | attempt=%d | raw_len=%d | preview=%.200s", attempt, len(raw), raw)
            try:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                data = json.loads(raw[start:end])
                report = MatchingReport.model_validate(data)
                if report.matched_skills or report.missing_skills:
                    return report
                logger.warning("skill_matcher | attempt=%d | parsed but all lists empty, retrying", attempt)
                last_exc = ValueError("all lists empty")
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                last_exc = exc
                logger.warning("skill_matcher | attempt=%d | parse error: %s", attempt, exc)
        logger.error("skill_matcher | failed after 3 attempts, returning empty report")
        return MatchingReport()
