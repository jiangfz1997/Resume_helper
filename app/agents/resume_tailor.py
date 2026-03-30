import json
from pathlib import Path
from typing import Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import (
    JobDescription,
    MasterProfile,
    MatchingReport,
    TailoredResumeDraft,
    WorkExperience,
    Project,
)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "resume_tailor.txt").read_text(encoding="utf-8")


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
    """Fix common LLM omissions before Pydantic validation.

    - experiences[*].location: None → ""
    - education: missing → copy from profile (overwritten by model_copy anyway)
    """
    for exp in result.get("experiences", []):
        if exp.get("location") is None:
            exp["location"] = ""
    if "education" not in result or result["education"] is None:
        result["education"] = [e.model_dump() for e in profile.educations]


class OllamaResumeTailor:
    def __init__(self) -> None:
        model = get_model_factory().build("resume_tailor")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

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
