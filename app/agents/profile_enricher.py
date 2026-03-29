import re
from calendar import month_abbr

from app.interfaces.base import IProfileEnricher
from app.models.data_models import ParsedProfileDraft, ProficiencyLevel, Skill

_MONTH_MAP: dict[str, str] = {
    name.lower(): f"{i:02d}" for i, name in enumerate(month_abbr) if name
}
_MONTH_MAP.update(
    {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }
)

_PROFICIENCY_RANK: dict[ProficiencyLevel, int] = {
    ProficiencyLevel.beginner: 0,
    ProficiencyLevel.intermediate: 1,
    ProficiencyLevel.expert: 2,
}

_KNOWN_TECH: list[str] = [
    "python", "java", "javascript", "typescript", "go", "rust", "c++", "c#", "ruby",
    "kotlin", "swift", "scala", "r", "matlab", "bash", "shell",
    "react", "vue", "angular", "next.js", "nuxt", "svelte",
    "fastapi", "django", "flask", "spring", "express", "nestjs", "rails",
    "postgresql", "mysql", "sqlite", "mongodb", "redis", "elasticsearch",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions",
    "aws", "azure", "gcp", "s3", "ec2", "lambda",
    "kafka", "rabbitmq", "celery",
    "langchain", "langgraph", "openai", "pytorch", "tensorflow", "scikit-learn",
    "graphql", "grpc", "rest", "websocket",
    "git", "linux", "nginx",
]


def _normalize_date(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return s

    # Already YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s

    # YYYY only
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01"

    # "Month YYYY" or "YYYY Month"
    m = re.search(r"([a-zA-Z]+)[.\s]+(\d{4})", s)
    if m:
        month_key = m.group(1).lower().rstrip(".")
        year = m.group(2)
        month_num = _MONTH_MAP.get(month_key)
        if month_num:
            return f"{year}-{month_num}"

    m = re.search(r"(\d{4})[.\s]+([a-zA-Z]+)", s)
    if m:
        year = m.group(1)
        month_key = m.group(2).lower().rstrip(".")
        month_num = _MONTH_MAP.get(month_key)
        if month_num:
            return f"{year}-{month_num}"

    return s


def _valid_proficiency(value: str | None) -> ProficiencyLevel:
    try:
        return ProficiencyLevel(value)
    except (ValueError, TypeError):
        return ProficiencyLevel.intermediate


def _deduplicate_skills(skills: list[Skill]) -> list[Skill]:
    best: dict[str, Skill] = {}
    for s in skills:
        key = s.name.lower()
        existing = best.get(key)
        if existing is None or _PROFICIENCY_RANK.get(s.proficiency, 0) > _PROFICIENCY_RANK.get(existing.proficiency, 0):
            best[key] = s
    return list(best.values())


def _extract_tech_from_text(text: str, existing_names: set[str]) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for tech in _KNOWN_TECH:
        if tech not in existing_names and re.search(r"\b" + re.escape(tech) + r"\b", lower):
            found.append(tech)
    return found


class CodeProfileEnricher(IProfileEnricher):
    """Pure-Python enricher — never calls an LLM, never modifies text content."""

    async def enrich(self, draft: ParsedProfileDraft) -> ParsedProfileDraft:
        data = draft.model_dump()

        # 1. DATE NORMALIZATION
        for exp in data["work_experiences"]:
            exp["start_date"] = _normalize_date(exp.get("start_date")) or ""
            exp["end_date"] = _normalize_date(exp.get("end_date"))
        for edu in data["educations"]:
            edu["start_date"] = _normalize_date(edu.get("start_date")) or ""
            edu["end_date"] = _normalize_date(edu.get("end_date"))

        # 2. PROFICIENCY VALIDATION
        for skill in data["skills"]:
            skill["proficiency"] = _valid_proficiency(skill.get("proficiency")).value

        # 3. SKILL DEDUPLICATION
        validated = [Skill(**s) for s in data["skills"]]
        deduped = _deduplicate_skills(validated)
        data["skills"] = [s.model_dump() for s in deduped]

        # 4. IMPLICIT SKILL EXTRACTION from experience + project descriptions
        existing_names = {s["name"].lower() for s in data["skills"]}
        new_skills: list[dict] = []
        for exp in data["work_experiences"]:
            for bullet in exp.get("description", []):
                for tech in _extract_tech_from_text(bullet, existing_names):
                    existing_names.add(tech)
                    new_skills.append({"category": "Tools & Technologies", "name": tech, "proficiency": "intermediate"})
        for proj in data["projects"]:
            description_text = proj.get("description", "")
            for tech in _extract_tech_from_text(description_text, existing_names):
                existing_names.add(tech)
                new_skills.append({"category": "Tools & Technologies", "name": tech, "proficiency": "intermediate"})
        data["skills"].extend(new_skills)

        # 5. PROJECT TECH STACK: fill if empty
        for proj in data["projects"]:
            if not proj.get("tech_stack"):
                description_text = proj.get("description", "")
                lower = description_text.lower()
                proj["tech_stack"] = [
                    tech for tech in _KNOWN_TECH
                    if re.search(r"\b" + re.escape(tech) + r"\b", lower)
                ]

        return ParsedProfileDraft.model_validate(data)
