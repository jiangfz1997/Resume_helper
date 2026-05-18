import json
import logging
from pathlib import Path
from typing import Literal, Optional, Union

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.date_utils import duration_months
from app.core.model_factory import get_model_factory
from app.models.data_models import (
    JobDescription,
    MasterProfile,
    MatchingReport,
    Project,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
    WorkExperience,
)

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent.parent / "prompts"
_prompt_text = (_PROMPTS / "resume_tailor.txt").read_text(encoding="utf-8")
_summary_prompt_text = (_PROMPTS / "resume_tailor_summary.txt").read_text(encoding="utf-8")
_tailor_one_prompt_text = (_PROMPTS / "resume_tailor_one.txt").read_text(encoding="utf-8")

_INTERN_KEYWORDS = {"intern", "internship", "co-op", "coop", "co op", "student"}


def _select_items(items: list, indices: list[int]) -> list:
    if not indices:
        return list(items)
    return [items[i] for i in indices if 0 <= i < len(items)]


def _build_profile_json(
    profile: MasterProfile,
    exp_indices: list[int],
    proj_indices: list[int],
) -> str:
    sorted_exp = _select_items(profile.work_experiences, exp_indices)
    sorted_proj = _select_items(profile.projects, proj_indices)
    data = {
        "work_experiences": [
            {
                "title": e.title,
                "company": e.company,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "description": e.description,
            }
            for e in sorted_exp
        ],
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "tech_stack": p.tech_stack,
                "url": p.url,
                "bullets": p.bullets,
            }
            for p in sorted_proj
        ],
        "skills": [{"name": s.name, "category": s.category} for s in profile.skills],
    }
    return json.dumps(data)


def _normalize_tailor_result(result: dict, profile: MasterProfile) -> None:
    for exp in result.get("experiences", []):
        if exp.get("location") is None:
            exp["location"] = ""
    if "education" not in result or result["education"] is None:
        result["education"] = [e.model_dump() for e in profile.educations]


def _exp_to_tailor(exp: WorkExperience) -> TailoredExperience:
    bullets = [TailoredBullet(text=b) for b in exp.description if b.strip()]
    return TailoredExperience(
        company=exp.company,
        title=exp.title,
        location="",
        start_date=exp.start_date,
        end_date=exp.end_date,
        bullets=bullets,
    )


def _proj_to_tailor(proj: Project) -> TailoredProject:
    bullets = [TailoredBullet(text=b) for b in proj.bullets if b.strip()]
    return TailoredProject(
        name=proj.name,
        description=proj.description,
        tech_stack=proj.tech_stack,
        url=proj.url,
        bullets=bullets,
    )


def _calc_experience_years(experiences: list[WorkExperience]) -> float:
    total = 0.0
    for exp in experiences:
        if any(kw in (exp.title or "").lower() for kw in _INTERN_KEYWORDS):
            continue
        total += duration_months(exp.start_date, exp.end_date)
    return round(total / 12, 1)


def assemble_base_draft(
    profile: MasterProfile,
    exp_indices: list[int],
    proj_indices: list[int],
    summary: str = "",
    template_id: Optional[object] = None,
    template_source: Optional[str] = None,
) -> TailoredResumeDraft:
    """Assemble a TailoredResumeDraft directly from raw profile data — no LLM involved."""
    exps = _select_items(profile.work_experiences, exp_indices)
    projs = _select_items(profile.projects, proj_indices)
    return TailoredResumeDraft(
        summary=summary,
        experiences=[_exp_to_tailor(e) for e in exps],
        education=profile.educations,
        projects=[_proj_to_tailor(p) for p in projs],
        skills=profile.skills,
        contact_info=profile.contact_info,
        template_id=template_id,
        template_source=template_source,
    )


class OllamaResumeTailor:
    def __init__(self) -> None:
        factory = get_model_factory()
        model = factory.build("resume_tailor")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

        summary_model = factory.build("resume_chat_stream")
        self._summary_chain = (
            ChatPromptTemplate.from_template(_summary_prompt_text)
            | summary_model
            | StrOutputParser()
        )

        tailor_one_model = factory.build("resume_tailor")
        self._tailor_one_chain = (
            ChatPromptTemplate.from_template(_tailor_one_prompt_text)
            | tailor_one_model
            | JsonOutputParser()
        )

    async def generate_summary(
        self,
        profile: MasterProfile,
        jd: JobDescription,
    ) -> str:
        """Generate a 2-3 sentence summary grounded in raw profile data."""
        if profile.summary:
            return profile.summary

        exp_years = _calc_experience_years(profile.work_experiences)
        current_title = profile.work_experiences[0].title if profile.work_experiences else "Candidate"
        top_skills = ", ".join(s.name for s in profile.skills[:8])

        raw = await self._summary_chain.ainvoke({
            "full_name": profile.full_name,
            "current_title": current_title,
            "experience_years": exp_years,
            "top_skills": top_skills or "N/A",
            "target_title": jd.title,
        })
        return raw.strip()

    async def tailor_one(
        self,
        item: Union[WorkExperience, Project],
        item_type: Literal["exp", "proj"],
        jd: JobDescription,
        report: MatchingReport,
    ) -> Union[TailoredExperience, TailoredProject]:
        """Optimize a single experience or project item against the JD."""
        if item_type == "exp":
            assert isinstance(item, WorkExperience)
            item_json = json.dumps({
                "company": item.company,
                "title": item.title,
                "location": "",
                "start_date": item.start_date,
                "end_date": item.end_date,
                "bullets": [{"text": b, "highlighted": False} for b in item.description if b.strip()],
            })
        else:
            assert isinstance(item, Project)
            item_json = json.dumps({
                "name": item.name,
                "description": item.description,
                "tech_stack": item.tech_stack,
                "url": item.url,
                "bullets": [{"text": b, "highlighted": False} for b in item.bullets if b.strip()],
            })

        result = await self._tailor_one_chain.ainvoke({
            "item_type": "experience" if item_type == "exp" else "project",
            "item_json": item_json,
            "jd_json": jd.model_dump_json(),
            "matched_skills": ", ".join(report.matched_skills[:10]),
            "missing_skills": ", ".join(report.missing_skills[:10]),
        })

        if item_type == "exp":
            if result.get("location") is None:
                result["location"] = ""
            return TailoredExperience.model_validate(result)
        return TailoredProject.model_validate(result)

    async def tailor(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        current_title: str,
        template_id: Optional[object] = None,
        template_source: Optional[str] = None,
        exp_indices: Optional[list[int]] = None,
        proj_indices: Optional[list[int]] = None,
    ) -> TailoredResumeDraft:
        profile_json = _build_profile_json(
            profile,
            exp_indices if exp_indices is not None else matching_report.topn_experience_indices,
            proj_indices if proj_indices is not None else matching_report.topn_project_indices,
        )
        result = await self._chain.ainvoke({
            "current_title": current_title,
            "profile_json": profile_json,
            "jd_json": jd.model_dump_json(),
            "matching_report_json": matching_report.model_dump_json(),
        })
        _normalize_tailor_result(result, profile)
        draft = TailoredResumeDraft.model_validate(result)
        return draft.model_copy(update={
            "education": profile.educations,
            "contact_info": profile.contact_info,
            "template_id": template_id,
            "template_source": template_source,
        })
