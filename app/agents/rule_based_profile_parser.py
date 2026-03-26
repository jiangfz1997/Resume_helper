import re

from app.interfaces.base import IProfileParser
from app.models.data_models import Education, ParsedProfileDraft, ProficiencyLevel, Project, Skill, WorkExperience

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------
_MONTH_PAT = (
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?'
    r'|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
)
_YEAR_PAT = r'(?:19|20)\d{2}'
_DATE_SINGLE = rf'(?:{_MONTH_PAT}\.?\s+{_YEAR_PAT}|{_YEAR_PAT})'
_DATE_END = rf'(?:{_DATE_SINGLE}|Present|Current|Now)'
_DATE_RANGE_RE = re.compile(
    rf'({_DATE_SINGLE})\s*[-–—/]\s*({_DATE_END})',
    re.IGNORECASE,
)
_DATE_SINGLE_RE = re.compile(rf'\b({_DATE_SINGLE})\b', re.IGNORECASE)

# Section headers
_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ('summary', re.compile(
        r'^(summary|professional\s+summary|objective|profile|about(\s+me)?)\s*:?\s*$',
        re.IGNORECASE,
    )),
    ('experience', re.compile(
        r'^(work\s+experience|professional\s+experience|employment(\s+history)?|experience)\s*:?\s*$',
        re.IGNORECASE,
    )),
    ('education', re.compile(
        r'^(education(al\s+background)?|academic(\s+background)?)\s*:?\s*$',
        re.IGNORECASE,
    )),
    ('projects', re.compile(
        r'^(projects?|personal\s+projects?|side\s+projects?|notable\s+projects?|selected\s+projects?)\s*:?\s*$',
        re.IGNORECASE,
    )),
    ('skills', re.compile(
        r'^(technical\s+skills?|skills?|technologies|core\s+competencies?|competencies?)\s*:?\s*$',
        re.IGNORECASE,
    )),
    ('certifications', re.compile(
        r'^(certifications?|licenses?|credentials?)\s*:?\s*$',
        re.IGNORECASE,
    )),
]

_BULLET_RE = re.compile(r'^[•·▪▸►○●\-\*\+]\s+(.+)$')
_GPA_RE = re.compile(r'\bGPA[:\s]+(\d+\.\d+)', re.IGNORECASE)
_DEGREE_KEYWORDS = [
    'bachelor', 'b.s.', 'b.sc', 'b.a.', 'b.eng', 'b.tech',
    'master', 'm.s.', 'm.sc', 'm.a.', 'm.eng', 'mba', 'm.tech',
    'ph.d', 'phd', 'doctor', 'associate', 'diploma', 'certificate',
]
_DEGREE_RE = re.compile(r'\b(' + '|'.join(re.escape(d) for d in _DEGREE_KEYWORDS) + r')\b', re.IGNORECASE)
_FIELD_RE = re.compile(r'\b(?:in|of)\s+([A-Za-z][A-Za-z\s,&]+?)(?:\s*,|\s*\.|\s*$)', re.IGNORECASE)
_URL_RE = re.compile(r'https?://\S+')


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line.strip()))


def _extract_bullet_text(line: str) -> str:
    m = _BULLET_RE.match(line.strip())
    return m.group(1).strip() if m else line.strip()


def _extract_date_range(text: str) -> tuple[str, str | None]:
    m = _DATE_RANGE_RE.search(text)
    if m:
        start = m.group(1).strip()
        end_raw = m.group(2).strip()
        end = None if re.match(r'^(present|current|now)$', end_raw, re.IGNORECASE) else end_raw
        return start, end
    m2 = _DATE_SINGLE_RE.search(text)
    if m2:
        return m2.group(1).strip(), None
    return '', None


def _strip_dates(text: str) -> str:
    text = _DATE_RANGE_RE.sub('', text)
    text = _DATE_SINGLE_RE.sub('', text)
    return re.sub(r'\s*[-–—|,]\s*$', '', text).strip(' |–—,-/')


def _has_date(line: str) -> bool:
    return bool(_DATE_RANGE_RE.search(line) or _DATE_SINGLE_RE.search(line))


class RuleBasedProfileParser(IProfileParser):
    """Deterministic, regex-based resume parser. No LLM calls."""

    async def parse(self, raw_text: str) -> ParsedProfileDraft:
        lines = [line.rstrip() for line in raw_text.splitlines()]
        sections = self._split_sections(lines)
        return ParsedProfileDraft(
            summary=self._parse_summary(sections.get('summary', [])) or None,
            work_experiences=self._parse_experience(sections.get('experience', [])),
            educations=self._parse_education(sections.get('education', [])),
            projects=self._parse_projects(sections.get('projects', [])),
            skills=self._parse_skills(sections.get('skills', [])),
        )

    # ------------------------------------------------------------------
    # Section splitting
    # ------------------------------------------------------------------

    def _split_sections(self, lines: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current = 'header'
        for line in lines:
            stripped = line.strip()
            matched: str | None = None
            for name, pat in _SECTION_PATTERNS:
                if pat.match(stripped):
                    matched = name
                    break
            if matched:
                current = matched
                sections.setdefault(current, [])
            else:
                sections.setdefault(current, []).append(line)
        return sections

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _parse_summary(self, lines: list[str]) -> str:
        return ' '.join(line.strip() for line in lines if line.strip())

    # ------------------------------------------------------------------
    # Work experience
    # ------------------------------------------------------------------

    def _parse_experience(self, lines: list[str]) -> list[WorkExperience]:
        entries = self._split_date_anchored_entries(lines)
        return [r for entry in entries if (r := self._parse_experience_entry(entry)) is not None]

    def _split_date_anchored_entries(self, lines: list[str]) -> list[list[str]]:
        """New entry begins at a non-bullet line that contains a date range,
        provided the current entry already contains a dated line."""
        entries: list[list[str]] = []
        current: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_date_line = _has_date(stripped) and not _is_bullet(stripped)
            current_has_date = any(_has_date(l) and not _is_bullet(l) for l in current)
            if is_date_line and current_has_date:
                entries.append(current)
                current = []
            current.append(stripped)

        if current:
            entries.append(current)
        return entries

    def _parse_experience_entry(self, lines: list[str]) -> WorkExperience | None:
        if not lines:
            return None

        header_lines: list[str] = []
        description: list[str] = []
        for line in lines:
            if _is_bullet(line):
                description.append(_extract_bullet_text(line))
            else:
                header_lines.append(line)

        # Locate the date line
        date_line_idx = next((i for i, l in enumerate(header_lines) if _has_date(l)), -1)

        title = ''
        company = ''
        start_date = ''
        end_date: str | None = None

        if date_line_idx >= 0:
            start_date, end_date = _extract_date_range(header_lines[date_line_idx])
            date_remainder = _strip_dates(header_lines[date_line_idx])
            pre = header_lines[:date_line_idx]
            post = header_lines[date_line_idx + 1:]

            if pre:
                parts = re.split(r'\s*[|@,]\s*', pre[0], maxsplit=1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else (pre[1].strip() if len(pre) > 1 else '')
            if not company:
                if date_remainder:
                    company = date_remainder
                elif post:
                    company = post[0]
        else:
            if header_lines:
                parts = re.split(r'\s*[|@,]\s*', header_lines[0], maxsplit=1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else (header_lines[1].strip() if len(header_lines) > 1 else '')

        if not title and not company:
            return None

        return WorkExperience(
            company=company or title,
            title=title or company,
            start_date=start_date,
            end_date=end_date,
            description=description,
        )

    # ------------------------------------------------------------------
    # Education
    # ------------------------------------------------------------------

    def _parse_education(self, lines: list[str]) -> list[Education]:
        entries = self._split_date_anchored_entries(lines)
        if not entries:
            entries = self._split_by_blank_or_degree(lines)
        return [r for entry in entries if (r := self._parse_education_entry(entry)) is not None]

    def _split_by_blank_or_degree(self, lines: list[str]) -> list[list[str]]:
        entries: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current:
                    entries.append(current)
                    current = []
            else:
                current.append(stripped)
        if current:
            entries.append(current)
        return entries

    def _parse_education_entry(self, lines: list[str]) -> Education | None:
        if not lines:
            return None

        institution = ''
        degree = ''
        field_of_study = ''
        start_date: str | None = None
        end_date: str | None = None
        gpa: str | None = None

        for line in lines:
            stripped = line.strip()
            gpa_m = _GPA_RE.search(stripped)
            if gpa_m:
                gpa = gpa_m.group(1)

            if _has_date(stripped) and not _is_bullet(stripped):
                start_date, end_date = _extract_date_range(stripped)
                remainder = _strip_dates(stripped)
                if remainder and not institution:
                    institution = remainder
                continue

            if _DEGREE_RE.search(stripped) and not degree:
                degree = stripped
                field_m = _FIELD_RE.search(stripped)
                if field_m:
                    field_of_study = field_m.group(1).strip().rstrip(',.')
                continue

            if not institution and not _is_bullet(stripped):
                institution = stripped

        if not institution and not degree:
            return None

        return Education(
            institution=institution,
            degree=degree,
            field_of_study=field_of_study,
            start_date=start_date,
            end_date=end_date,
            gpa=gpa,
        )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def _parse_projects(self, lines: list[str]) -> list[Project]:
        entries = self._split_project_entries(lines)
        return [r for entry in entries if (r := self._parse_project_entry(entry)) is not None]

    def _split_project_entries(self, lines: list[str]) -> list[list[str]]:
        """New project entry starts at a non-bullet line that follows bullet lines."""
        entries: list[list[str]] = []
        current: list[str] = []
        seen_bullet = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _is_bullet(stripped):
                seen_bullet = True
                current.append(stripped)
            else:
                if seen_bullet and current:
                    entries.append(current)
                    current = []
                    seen_bullet = False
                current.append(stripped)

        if current:
            entries.append(current)
        return entries

    def _parse_project_entry(self, lines: list[str]) -> Project | None:
        if not lines:
            return None

        name = ''
        description = ''
        bullets: list[str] = []
        tech_stack: list[str] = []
        url: str | None = None

        for line in lines:
            stripped = line.strip()
            if _is_bullet(stripped):
                bullets.append(_extract_bullet_text(stripped))
                continue

            url_m = _URL_RE.search(stripped)
            if url_m and not url:
                url = url_m.group(0)
                stripped = stripped.replace(url_m.group(0), '').strip(' |:-')

            if not name:
                parts = re.split(r'\s*[|:]\s*', stripped, maxsplit=1)
                name = parts[0].strip()
                if len(parts) > 1:
                    rest = parts[1].strip()
                    if _URL_RE.match(rest):
                        url = rest
                    elif ',' in rest or re.search(r'\b[A-Z][a-z]+\b', rest):
                        tech_stack = [t.strip() for t in re.split(r'[,;]\s*', rest) if t.strip()]
                    else:
                        description = rest
            elif not description:
                description = stripped

        if not name:
            return None

        return Project(
            name=name,
            description=description or (bullets[0] if bullets else ''),
            bullets=bullets,
            tech_stack=tech_stack,
            url=url,
        )

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def _parse_skills(self, lines: list[str]) -> list[Skill]:
        skills: list[Skill] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _is_bullet(stripped):
                stripped = _extract_bullet_text(stripped)

            # "Category: skill1, skill2" format
            colon_m = re.match(r'^([^:]{3,40}):\s*(.+)$', stripped)
            if colon_m:
                category = colon_m.group(1).strip()
                for name in re.split(r'[,;|]\s*', colon_m.group(2)):
                    name = name.strip()
                    if name:
                        skills.append(Skill(category=category, name=name, proficiency=ProficiencyLevel.intermediate))
            elif ',' in stripped or ';' in stripped:
                for name in re.split(r'[,;]\s*', stripped):
                    name = name.strip()
                    if name:
                        skills.append(Skill(category='Technical Skills', name=name, proficiency=ProficiencyLevel.intermediate))
            elif stripped:
                skills.append(Skill(category='Technical Skills', name=stripped, proficiency=ProficiencyLevel.intermediate))
        return skills
