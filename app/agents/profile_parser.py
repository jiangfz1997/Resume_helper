import asyncio
import logging
from pathlib import Path
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.model_factory import get_model_factory
from app.interfaces.base import IProfileParser
from app.models.data_models import Education, ParsedProfileDraft, Project, Skill, WorkExperience

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def _load(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Structured output schemas — wrapper models required by with_structured_output
# ---------------------------------------------------------------------------

class _SectionHeaders(BaseModel):
    summary: Optional[int] = None
    experience: Optional[int] = None
    education: Optional[int] = None
    projects: Optional[int] = None
    skills: Optional[int] = None


class _WorkExperienceList(BaseModel):
    items: list[WorkExperience]


class _EducationList(BaseModel):
    items: list[Education]


class _ProjectList(BaseModel):
    items: list[Project]


class _SkillList(BaseModel):
    items: list[Skill]


# ---------------------------------------------------------------------------

class TwoPhaseProfileParser(IProfileParser):
    """
    Phase 1: one LLM call identifies section header line indices.
    Phase 2: four parallel LLM calls parse each section with CoT prompts.
    Both phases use with_structured_output() to enforce Pydantic schemas at
    generation time — no post-hoc validation failures possible.
    """

    def __init__(self) -> None:
        factory = get_model_factory()
        detector_llm = factory.build("section_detector")
        parser_llm = factory.build("section_parser")

        self._detector = (
            ChatPromptTemplate.from_template(_load("section_header_detector.txt"))
            | detector_llm.with_structured_output(_SectionHeaders)
        )
        self._exp_chain = (
            ChatPromptTemplate.from_template(_load("parse_experience_section.txt"))
            | parser_llm.with_structured_output(_WorkExperienceList)
        )
        self._edu_chain = (
            ChatPromptTemplate.from_template(_load("parse_education_section.txt"))
            | parser_llm.with_structured_output(_EducationList)
        )
        self._proj_chain = (
            ChatPromptTemplate.from_template(_load("parse_projects_section.txt"))
            | parser_llm.with_structured_output(_ProjectList)
        )
        self._skills_chain = (
            ChatPromptTemplate.from_template(_load("parse_skills_section.txt"))
            | parser_llm.with_structured_output(_SkillList)
        )

    async def parse(self, raw_text: str) -> ParsedProfileDraft:
        lines = raw_text.splitlines()
        numbered = "\n".join(
            f"[{i}] {line}" for i, line in enumerate(lines) if line.strip()
        )

        logger.debug("TwoPhaseProfileParser | phase1 | total_lines=%d", len(lines))
        headers: _SectionHeaders = await self._detector.ainvoke({"text": numbered})
        logger.debug("TwoPhaseProfileParser | headers=%s", headers.model_dump())

        sections = self._split_sections(lines, headers)
        logger.debug(
            "TwoPhaseProfileParser | phase2 | sections=%s",
            {k: len(v.splitlines()) for k, v in sections.items()},
        )

        exp_result, edu_result, proj_result, skills_result = await asyncio.gather(
            self._invoke(self._exp_chain, sections.get("experience", "")),
            self._invoke(self._edu_chain, sections.get("education", "")),
            self._invoke(self._proj_chain, sections.get("projects", "")),
            self._invoke(self._skills_chain, sections.get("skills", "")),
        )

        summary_text = sections.get("summary", "")
        return ParsedProfileDraft(
            summary=" ".join(summary_text.split()) or None,
            work_experiences=(exp_result.items if exp_result else []),
            educations=(edu_result.items if edu_result else []),
            projects=(proj_result.items if proj_result else []),
            skills=(skills_result.items if skills_result else []),
        )

    # ------------------------------------------------------------------

    def _split_sections(self, lines: list[str], headers: _SectionHeaders) -> dict[str, str]:
        header_dict = {k: v for k, v in headers.model_dump().items() if isinstance(v, int)}
        boundaries = sorted(header_dict.items(), key=lambda x: x[1])
        result: dict[str, str] = {}
        for i, (name, start) in enumerate(boundaries):
            content_start = start + 1
            content_end = boundaries[i + 1][1] if i + 1 < len(boundaries) else len(lines)
            content = "\n".join(
                line for line in lines[content_start:content_end] if line.strip()
            )
            result[name] = content
        return result

    async def _invoke(self, chain, text: str) -> BaseModel | None:
        if not text.strip():
            return None
        try:
            return await chain.ainvoke({"section_text": text})
        except Exception as exc:
            logger.warning("TwoPhaseProfileParser | section error: %s", exc)
            return None
