import json
import logging
from pathlib import Path

import pydantic
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import (
    AuditFeedback,
    Education,
    JobDescription,
    MasterProfile,
    MatchingReport,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
)

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "content_drafter.txt").read_text(
    encoding="utf-8"
)

_FEEDBACK_SECTION_TEMPLATE = """Previous Audit Feedback (iteration {iteration}):
Score: {score}
Suggestions:
{suggestions}

Revise the draft to address the suggestions above.
"""


def _build_profile_text(profile: MasterProfile) -> str:
    lines: list[str] = [f"Candidate: {profile.full_name}"]

    lines.append("\n=== WORK EXPERIENCES ===")
    for i, exp in enumerate(profile.work_experiences, 1):
        end = exp.end_date or "Present"
        lines.append(f"\n[Experience {i}]")
        lines.append(f"Company: {exp.company}")
        lines.append(f"Title: {exp.title}")
        lines.append(f"Dates: {exp.start_date} - {end}")
        if exp.description:
            lines.append("Bullets:")
            for b in exp.description:
                lines.append(f"  - {b}")

    lines.append("\n=== EDUCATION ===")
    for i, edu in enumerate(profile.educations, 1):
        end = edu.end_date or "Present"
        lines.append(f"\n[Education {i}]")
        lines.append(f"Institution: {edu.institution}")
        lines.append(f"Degree: {edu.degree}")
        lines.append(f"Field: {edu.field_of_study}")
        lines.append(f"Dates: {edu.start_date} - {end}")
        if edu.gpa:
            lines.append(f"GPA: {edu.gpa}")

    lines.append("\n=== PROJECTS ===")
    for i, proj in enumerate(profile.projects, 1):
        lines.append(f"\n[Project {i}]")
        lines.append(f"Name: {proj.name}")
        lines.append(f"Description: {proj.description}")
        if proj.bullets:
            lines.append("Bullets:")
            for b in proj.bullets:
                lines.append(f"  - {b}")
        if proj.tech_stack:
            lines.append(f"Tech: {', '.join(proj.tech_stack)}")
        if proj.url:
            lines.append(f"URL: {proj.url}")

    lines.append("\n=== SKILLS ===")
    by_cat: dict[str, list[str]] = {}
    for sk in profile.skills:
        by_cat.setdefault(sk.category, []).append(f"{sk.name} ({sk.proficiency})")
    for cat, names in by_cat.items():
        lines.append(f"{cat}: {', '.join(names)}")

    return "\n".join(lines)


def _build_allowlists(profile: MasterProfile) -> str:
    companies = ", ".join(f'"{e.company}"' for e in profile.work_experiences) or "none"
    institutions = ", ".join(f'"{e.institution}"' for e in profile.educations) or "none"
    projects = ", ".join(f'"{p.name}"' for p in profile.projects) or "none"
    return (
        f"ALLOWED company names (use ONLY these, verbatim): {companies}\n"
        f"ALLOWED institution names (use ONLY these, verbatim): {institutions}\n"
        f"ALLOWED project names (use ONLY these, verbatim): {projects}"
    )


def _validate_draft(draft: TailoredResumeDraft, profile: MasterProfile) -> list[str]:
    errors: list[str] = []
    valid_companies = {e.company.lower() for e in profile.work_experiences}
    for exp in draft.experiences:
        if exp.company.lower() not in valid_companies:
            errors.append(f"Invented company '{exp.company}' not in profile")
    valid_institutions = {e.institution.lower() for e in profile.educations}
    for edu in draft.education:
        if edu.institution.lower() not in valid_institutions:
            errors.append(f"Invented institution '{edu.institution}' not in profile")
    valid_projects = {p.name.lower() for p in profile.projects}
    for proj in draft.projects:
        if proj.name.lower() not in valid_projects:
            errors.append(f"Invented project '{proj.name}' not in profile")
    return errors


def _force_fix_draft(draft: TailoredResumeDraft, profile: MasterProfile) -> TailoredResumeDraft:
    """
    Deterministically overwrite fact fields (company, institution, project name, dates, gpa)
    with values from the profile. Bullet text produced by the LLM is preserved where possible.
    This is the last-resort fallback when the LLM keeps hallucinating names.
    """
    company_index = {e.company.lower(): e for e in profile.work_experiences}

    fixed_experiences: list[TailoredExperience] = []
    for i, exp_draft in enumerate(draft.experiences):
        src = company_index.get(exp_draft.company.lower())
        if src is None:
            src = profile.work_experiences[i] if i < len(profile.work_experiences) else None
        if src is None:
            continue
        fixed_experiences.append(
            TailoredExperience(
                company=src.company,
                title=src.title,
                location=exp_draft.location,
                start_date=src.start_date,
                end_date=src.end_date,
                bullets=exp_draft.bullets or [
                    TailoredBullet(text=b, highlighted=False) for b in src.description
                ],
            )
        )
    # ensure all profile experiences are represented
    represented = {e.company for e in fixed_experiences}
    for src in profile.work_experiences:
        if src.company not in represented:
            fixed_experiences.append(
                TailoredExperience(
                    company=src.company,
                    title=src.title,
                    location="",
                    start_date=src.start_date,
                    end_date=src.end_date,
                    bullets=[TailoredBullet(text=b, highlighted=False) for b in src.description],
                )
            )

    fixed_education: list[Education] = []
    inst_index = {e.institution.lower(): e for e in profile.educations}
    for i, edu_draft in enumerate(draft.education):
        src = inst_index.get(edu_draft.institution.lower())
        if src is None:
            src = profile.educations[i] if i < len(profile.educations) else None
        if src is None:
            continue
        fixed_education.append(
            Education(
                institution=src.institution,
                degree=src.degree,
                field_of_study=src.field_of_study,
                start_date=src.start_date,
                end_date=src.end_date,
                gpa=src.gpa,
            )
        )
    if not fixed_education:
        fixed_education = list(profile.educations)

    proj_index = {p.name.lower(): p for p in profile.projects}
    fixed_projects: list[TailoredProject] = []
    for i, proj_draft in enumerate(draft.projects):
        src = proj_index.get(proj_draft.name.lower())
        if src is None:
            src = profile.projects[i] if i < len(profile.projects) else None
        if src is None:
            continue
        fixed_projects.append(
            TailoredProject(
                name=src.name,
                description=src.description,
                tech_stack=src.tech_stack,
                url=src.url,
                bullets=proj_draft.bullets or [
                    TailoredBullet(text=b, highlighted=False) for b in src.bullets
                ],
            )
        )
    represented_proj = {p.name for p in fixed_projects}
    for src in profile.projects:
        if src.name not in represented_proj:
            fixed_projects.append(
                TailoredProject(
                    name=src.name,
                    description=src.description,
                    tech_stack=src.tech_stack,
                    url=src.url,
                    bullets=[TailoredBullet(text=b, highlighted=False) for b in src.bullets],
                )
            )

    return draft.model_copy(update={
        "experiences": fixed_experiences,
        "education": fixed_education,
        "projects": fixed_projects,
    })


class OllamaContentDrafter:
    def __init__(self) -> None:
        model = get_model_factory().build("content_drafter")
        self._chain = ChatPromptTemplate.from_template(_prompt_text) | model | StrOutputParser()

    async def draft(
        self,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        feedback: AuditFeedback | None = None,
        iteration: int = 0,
    ) -> TailoredResumeDraft:
        feedback_section = ""
        if feedback is not None:
            suggestions_text = "\n".join(f"- {s}" for s in feedback.suggestions)
            feedback_section = _FEEDBACK_SECTION_TEMPLATE.format(
                iteration=iteration,
                score=feedback.score,
                suggestions=suggestions_text,
            )

        invoke_input = {
            "profile_text": _build_profile_text(profile),
            "allowlists": _build_allowlists(profile),
            "jd_json": jd.model_dump_json(indent=2),
            "matching_report_json": matching_report.model_dump_json(indent=2),
            "feedback_section": feedback_section,
        }

        last_draft: TailoredResumeDraft | None = None

        for attempt in range(3):
            raw = await self._chain.ainvoke(invoke_input)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()

            try:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                data = json.loads(raw[start:end])
                draft = TailoredResumeDraft(
                    **data,
                    template_id=None,
                    template_source=None,
                )
                last_draft = draft
                violations = _validate_draft(draft, profile)
                if not violations:
                    logger.debug("content_drafter | ok | attempt=%d", attempt)
                    return draft
                logger.warning(
                    "content_drafter | hallucination attempt=%d | %s",
                    attempt, "; ".join(violations),
                )
                invoke_input = {
                    **invoke_input,
                    "feedback_section": (
                        feedback_section
                        + f"\nCRITICAL ERROR in your last response: {'; '.join(violations)}. "
                        "Use ONLY the names from the allowlists. Do NOT invent any names."
                    ),
                }
            except (json.JSONDecodeError, pydantic.ValidationError, ValueError, KeyError) as exc:
                logger.warning(
                    "content_drafter | parse failed attempt=%d | %s | raw_len=%d",
                    attempt, exc, len(raw),
                )
                invoke_input = {
                    **invoke_input,
                    "feedback_section": (
                        feedback_section
                        + "\nIMPORTANT: Your previous response was not valid JSON. "
                        "Return only a single JSON object, no explanation, no markdown."
                    ),
                }

        if last_draft is not None:
            logger.warning("content_drafter | applying deterministic fix after %d failed attempts", 3)
            return _force_fix_draft(last_draft, profile)

        raise ValueError("content_drafter failed to produce any parseable JSON after 3 attempts")
