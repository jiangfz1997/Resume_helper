"""Deterministic years-of-experience extraction from a job description.

Runs at ingest time, before any LLM call, so the years filter in filters.py can
reject an over-senior posting without spending a scoring request on it. Measured
against all 467 records in job-discovery-records on 2026-08-09: 71.7% of
descriptions yield a parsed requirement, 11.1% mention a duration this module
cannot parse, and 17.1% state none at all. On the 85 records where the LLM had
also stored a value, this agrees with it 94% of the time.

The single most important detail here is _ESCAPED_PLUS / _ESCAPED_DASH.
jobspy stores descriptions as markdown (description_format="markdown" in
sources/jobspy_source.py) and its converter escapes "+" and "-", so real rows
read "8\\+ years" and "3\\-5 years". An extractor that does not tolerate the
backslash silently drops every plus and range form -- on this corpus that one
detail is worth roughly 30 points of coverage.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Anything above this is not a hiring requirement. Real postings top out
# around 15; larger numbers come from company-tenure prose ("40 years in
# business"), which COMPANY_AGE_PREFIX below catches only when the giveaway
# wording is present. This is a noise guard and is deliberately NOT the user's
# filter threshold -- that lives in FilterConfig.max_required_years. Lowering
# this to match a search preference would turn "12 years required" into an
# extraction failure, sending the most senior postings to manual review
# instead of excluding them.
MAX_PLAUSIBLE_YEARS = 20

_WORD_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
}

_NUMBER = r"(?:\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")"
_YEARS = r"(?:years?|yrs?\.?|yoe)"
_ESCAPED_PLUS = r"\\?\+"
_ESCAPED_DASH = r"(?:\\?-|to|\u2013|\u2014)"

# Strongest first. _extract_hits() suppresses any later match overlapping an
# earlier one, so "3\-5 years" is read once as a 3..5 range instead of also
# producing a bare "5 years" hit -- that double-count was the cause of nearly
# every disagreement with the LLM in the 2026-08-09 probe.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("range", re.compile(rf"\b({_NUMBER})\s*{_ESCAPED_DASH}\s*({_NUMBER})\s*{_ESCAPED_PLUS}?\s*{_YEARS}", re.I)),
    ("plus", re.compile(rf"\b({_NUMBER})\s*{_ESCAPED_PLUS}\s*{_YEARS}", re.I)),
    ("plus_suffix", re.compile(rf"\b({_NUMBER})\s*{_YEARS}\s*(?:or more|{_ESCAPED_PLUS}|and above|and up)", re.I)),
    (
        "minimum",
        re.compile(rf"\b(?:minimum|min\.?|at least|no less than)\s*(?:of\s*)?({_NUMBER})\s*{_YEARS}", re.I),
    ),
    ("or_more", re.compile(rf"\b({_NUMBER})\s*(?:or more|or greater|and above|or above)\s*{_YEARS}", re.I)),
    # "Five (5\) years" -- the parenthesised digit restates the spelled word.
    (
        "paren",
        re.compile(rf"\b(?:{'|'.join(_WORD_NUMBERS)})\s*\(\s*(\d{{1,2}})\s*\\?\)\s*{_YEARS}", re.I),
    ),
    ("hyphen_adjective", re.compile(rf"\b({_NUMBER})\s*\\?-\s*{_YEARS}\s*(?:minimum|min\.?)", re.I)),
    ("bare", re.compile(rf"\b({_NUMBER})\s*{_YEARS}\b", re.I)),
)

# A duration only states a requirement when the surrounding text is about
# experience. Without this, "our 30 years of excellence" reads as a 30-year bar.
_EXPERIENCE_NEAR = re.compile(r"\bexperien\w*\b", re.I)
# Only unambiguous company-tenure openers. "for" and "over" were here first and
# silently killed "Looking for 3-5 years of experience", one of the most common
# phrasings in the corpus. MAX_PLAUSIBLE_YEARS already rejects the 30- and
# 40-year boilerplate this was written for, so it can afford to be narrow.
_COMPANY_AGE_PREFIX = re.compile(r"\b(?:founded|since|celebrat\w*|in business(?:\s+for)?)\s+(?:\w+\s+){0,3}$", re.I)

# A heading applies to everything under it, so it is only ever looked for
# BEFORE a hit. Searching symmetrically let a later "Preferred qualifications:"
# mark the required item above it as optional.
_PREFERRED_HEADING = re.compile(r"\b(preferred|nice[- ]to[- ]have|bonus|desirable|assets?)\b", re.I)
# Trailing qualifiers attach to the hit they follow. Bounded by [^.] so the
# match cannot cross a sentence boundary into the next bullet's heading.
_PREFERRED_TRAILING = re.compile(
    r"^[^.]{0,40}\b(is a plus|an asset|preferred|desirable|nice[- ]to[- ]have)\b", re.I
)

_CONTEXT_WINDOW = 120
_TRAILING_WINDOW = 60


class YearsHit(BaseModel):
    """One parsed duration plus enough context to re-decide later. Kept in
    full on the candidate so the aggregation rule can change without
    re-scraping, the same reason filters label instead of delete."""

    pattern: str
    minimum: int
    maximum: int | None = None
    preferred: bool = False
    snippet: str


class YearsRequirement(BaseModel):
    """minimum/maximum are None when nothing parseable was found. `mentioned`
    separates "the posting states no requirement" from "it states one we could
    not read" -- only the latter deserves a manual look."""

    minimum: int | None = None
    maximum: int | None = None
    mentioned: bool = False
    hits: list[YearsHit] = Field(default_factory=list)

    @property
    def unparsed_mention(self) -> bool:
        return self.mentioned and self.minimum is None


def _to_int(token: str) -> int | None:
    token = token.strip().casefold()
    if token.isdigit():
        value = int(token)
        return value if 0 < value <= MAX_PLAUSIBLE_YEARS else None
    return _WORD_NUMBERS.get(token)


def _extract_hits(text: str) -> list[YearsHit]:
    hits: list[YearsHit] = []
    claimed: list[tuple[int, int]] = []

    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in claimed):
                continue
            minimum = _to_int(match.group(1))
            if minimum is None:
                continue
            claimed.append((match.start(), match.end()))

            before = text[max(0, match.start() - _CONTEXT_WINDOW) : match.start()]
            after = text[match.end() : match.end() + _TRAILING_WINDOW]
            window = text[max(0, match.start() - _CONTEXT_WINDOW) : match.end() + _CONTEXT_WINDOW]
            if not _EXPERIENCE_NEAR.search(window) or _COMPANY_AGE_PREFIX.search(before):
                continue

            maximum = _to_int(match.group(2)) if pattern.groups > 1 else None
            hits.append(
                YearsHit(
                    pattern=name,
                    minimum=minimum,
                    maximum=maximum,
                    preferred=bool(_PREFERRED_HEADING.search(before) or _PREFERRED_TRAILING.search(after)),
                    snippet=" ".join(match.group(0).split()),
                )
            )
    return hits


def extract_years(description: str | None) -> YearsRequirement:
    """Aggregate every parsed duration into one binding requirement.

    Takes the maximum of the non-preferred minimums: a posting listing "7+
    years backend" and "4+ years Python" demands both, so 7 is the bar. Probe
    on 2026-08-09 confirmed this empirically -- max matched the LLM on 94% of
    comparable records against 83% for min.
    """
    if not description:
        return YearsRequirement()

    hits = _extract_hits(description)
    mentioned = bool(hits) or bool(re.search(rf"\b{_YEARS}\b", description, re.I))
    if not hits:
        return YearsRequirement(mentioned=mentioned)

    binding = [hit for hit in hits if not hit.preferred] or hits
    minimum = max(hit.minimum for hit in binding)
    # Pair the ceiling with the hit that set the floor rather than taking the
    # global max, so "3-5 years" plus "7+ years" reports 7..None, not 7..5.
    maximum = next((hit.maximum for hit in binding if hit.minimum == minimum and hit.maximum is not None), None)

    return YearsRequirement(minimum=minimum, maximum=maximum, mentioned=True, hits=hits)
