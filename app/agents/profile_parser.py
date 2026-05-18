import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from app.core.concurrency import get_llm_semaphore

from langchain_core.output_parsers import StrOutputParser
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
    Phase 1: one LLM call identifies section header line indices (structured output).
    Phase 2: four parallel LLM calls parse each section as free-text JSON,
    then validated with Pydantic. Free-text avoids truncation of long bullet arrays
    that occurs with structured output / function calling mode.
    """

    def __init__(self) -> None:
        factory = get_model_factory()
        # Phase 1: structured output is safe — only 5 integer fields, small payload
        detector_llm = factory.build_chat_model("section_detector")
        self._detector = (
            ChatPromptTemplate.from_template(_load("section_header_detector.txt"))
            | detector_llm.with_structured_output(_SectionHeaders)
        )
        # Phase 2: free-text JSON — structured output truncates long bullet arrays
        parser_model = factory.build("section_parser")
        _str = StrOutputParser()
        self._exp_chain = (
            ChatPromptTemplate.from_template(_load("parse_experience_section.txt"))
            | parser_model | _str
        )
        self._edu_chain = (
            ChatPromptTemplate.from_template(_load("parse_education_section.txt"))
            | parser_model | _str
        )
        self._proj_chain = (
            ChatPromptTemplate.from_template(_load("parse_projects_section.txt"))
            | parser_model | _str
        )
        self._skills_chain = (
            ChatPromptTemplate.from_template(_load("parse_skills_section.txt"))
            | parser_model | _str
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

        sem = get_llm_semaphore()

        async def _guarded(coro):
            async with sem:
                return await coro

        exp_result, edu_result, proj_result, skills_result = await asyncio.gather(
            _guarded(self._invoke(self._exp_chain, sections.get("experience", ""), _WorkExperienceList)),
            _guarded(self._invoke(self._edu_chain, sections.get("education", ""), _EducationList)),
            _guarded(self._invoke(self._proj_chain, sections.get("projects", ""), _ProjectList)),
            _guarded(self._invoke(self._skills_chain, sections.get("skills", ""), _SkillList)),
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
            raw = "\n".join(
                line for line in lines[content_start:content_end] if line.strip()
            )
            result[name] = self._rejoin_wrapped_lines(raw)
        return result

    @staticmethod
    def _rejoin_wrapped_lines(text: str) -> str:
        """Join PDF word-wrapped continuation lines before passing to the LLM.

        A line is a continuation of the previous if:
        - Previous ends with a hard hyphen and current starts lowercase
          (e.g. "high-" + "frequency" → "high-frequency")
        - Previous does not end with sentence-ending punctuation (.!?:)
          and current starts lowercase (soft wrap).
        Lines starting with uppercase are always treated as a new entry.
        """
        _SENTENCE_END = frozenset('.!?:')
        joined: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if joined:
                prev = joined[-1]
                if prev.endswith('-') and stripped[0].islower():
                    joined[-1] = prev[:-1] + stripped
                    continue
                if prev[-1] not in _SENTENCE_END and stripped[0].islower():
                    joined[-1] = prev + ' ' + stripped
                    continue
            joined.append(stripped)
        return '\n'.join(joined)

    async def _invoke(self, chain, text: str, schema: type[BaseModel]) -> BaseModel | None:
        if not text.strip():
            return None
        try:
            raw: str = await chain.ainvoke({"section_text": text})
            logger.debug(
                "TwoPhaseProfileParser | section raw | schema=%s len=%d preview=%.300s",
                schema.__name__, len(raw), raw,
            )
            # Try object form first: {"items": [...]}
            try:
                obj_start = raw.index("{")
                obj_end = raw.rindex("}") + 1
                data = json.loads(raw[obj_start:obj_end])
                if "items" in data:
                    return schema.model_validate(data)
            except (ValueError, json.JSONDecodeError):
                pass
            # Fallback: bare array [...] — wrap it
            arr_start = raw.index("[")
            arr_end = raw.rindex("]") + 1
            items = json.loads(raw[arr_start:arr_end])
            return schema.model_validate({"items": items})
        except Exception as exc:
            logger.warning(
                "TwoPhaseProfileParser | section parse error | schema=%s | %s | raw=%.500s",
                schema.__name__, exc, raw if "raw" in dir() else "(no raw)",
            )
            return None
