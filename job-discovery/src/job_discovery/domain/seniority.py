"""Deterministic new-grad detection.

Separate from years.py on purpose. A probe over all 467 records on 2026-08-09
showed the two signals barely overlap: 15 postings carry explicit new-grad
language, 101 ask for three years or less, and only 5 do both. The low-years
group is full of "Software Engineer II", "Intermediate Quality Engineer" and
"Data Engineer II" -- low bar, not new grad. Collapsing them into one tag would
mislabel that whole group.

The tag earns its place by covering years.py's blind spot: 10 of the 15 genuine
new-grad postings state no year requirement at all (internships and co-ops
rarely do), so without this they would fall into the unparsed-mention bucket
and sit in manual review -- exactly the postings a new grad most wants to see.

Canadian postings come through in French as well ("Stagiaire", "Developpeur
junior"), so the vocabularies below carry both languages.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Title vocabulary. "associate" is excluded deliberately: in this corpus it
# reads as a job grade at consultancies far more often than as an entry level.
_TITLE_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("new_grad_title", re.compile(r"\b(new[ \-]?grad\w*|graduate program\w*)\b", re.I)),
    ("entry_level_title", re.compile(r"\b(entry[ \-]level|early[ \-]career|débutant\w*)\b", re.I)),
    ("junior_title", re.compile(r"\b(junior|jr\.?)\b", re.I)),
    ("intern_title", re.compile(r"\b(intern|internship|co[ \-]?op|stagiaire|stage)\b", re.I)),
)

# Description vocabulary. Narrower than the title list: a description mentions
# "junior" for all sorts of reasons ("you will mentor junior engineers"), so
# only phrasing that names the hiring target counts here.
_DESCRIPTION_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("new_grad_text", re.compile(r"\b(new[ \-]?grad\w*|recent(ly)? graduat\w*|university graduat\w*)\b", re.I)),
    ("campus_text", re.compile(r"\b(campus (hire|recruit\w*)|graduating (in|students)|final[ \-]year student)\b", re.I)),
    ("entry_level_text", re.compile(r"\b(entry[ \-]level|early[ \-]career)\b", re.I)),
    ("no_experience_text", re.compile(r"\bno (prior )?experience (is )?(required|necessary)\b", re.I)),
    ("french_text", re.compile(r"\b(nouveau diplôm\w*|jeune diplôm\w*|débutant\w* accept\w*)\b", re.I)),
)

# A senior marker in the title vetoes everything above. "Senior Engineer -
# mentoring our junior team" must not read as new grad.
_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head of|expert|iii|iv|v)\b", re.I
)


class SeniorityAssessment(BaseModel):
    """`signals` names every rule that fired, so a surprising tag on the
    dashboard can be explained without re-running the extractor."""

    is_new_grad: bool = False
    signals: list[str] = Field(default_factory=list)


def assess_seniority(title: str, description: str | None) -> SeniorityAssessment:
    if _SENIOR_TITLE.search(title):
        return SeniorityAssessment()

    signals = [name for name, pattern in _TITLE_SIGNALS if pattern.search(title)]
    if description:
        signals += [name for name, pattern in _DESCRIPTION_SIGNALS if pattern.search(description)]

    return SeniorityAssessment(is_new_grad=bool(signals), signals=signals)
