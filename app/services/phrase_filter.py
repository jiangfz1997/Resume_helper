import copy
import logging
import re
from typing import Final

from app.interfaces.base import IDraftPostProcessor
from app.models.data_models import TailoredResumeDraft

logger = logging.getLogger(__name__)

# Maps AI-sounding phrases to plain alternatives.
# Sorted by descending length at build time so multi-word phrases are matched
# before any of their constituent words.
_REPLACEMENTS: Final[dict[str, str]] = {
    # Multi-word phrases first (length matters for ordering)
    "paradigm shift": "change",
    "best-in-class": "top-performing",
    "world-class": "high-quality",
    "cutting-edge": "modern",
    "bleeding-edge": "modern",
    "game-changing": "innovative",
    "game-changer": "innovation",
    "move the needle": "make progress",
    "low-hanging fruit": "quick wins",
    "circle back": "follow up",
    "touch base": "connect",
    "deep dive": "analysis",
    "value-add": "benefit",
    "in order to": "to",
    "for the purpose of": "to",
    "with a view to": "to",
    "at the end of the day": "",
    "moving forward": "",
    "going forward": "",
    "on a daily basis": "daily",
    "on a regular basis": "regularly",
    "in a timely manner": "promptly",
    "at this point in time": "now",
    "due to the fact that": "because",
    "in the event that": "if",
    "in light of the fact that": "since",
    # Single-word replacements
    "spearheaded": "led",
    "orchestrated": "coordinated",
    "orchestrate": "coordinate",
    "orchestrating": "coordinating",
    "championed": "advocated for",
    "synergized": "collaborated",
    "leveraged": "used",
    "revolutionized": "transformed",
    "pioneered": "introduced",
    "catalyzed": "initiated",
    "operationalized": "implemented",
    "architected": "designed",
    "envisioned": "planned",
    "effectuated": "completed",
    "endeavored": "worked",
    "facilitated": "helped",
    "utilized": "used",
    "utilizing": "using",
    "synergy": "collaboration",
    "synergies": "collaborations",
    "paradigm": "approach",
    "holistic": "comprehensive",
    "robust": "strong",
    "scalable": "expandable",
    "actionable": "practical",
    "impactful": "effective",
    "proactively": "actively",
    "proactive": "active",
    "stakeholder": "team member",
    "deliverables": "outputs",
    "bandwidth": "capacity",
    "disruptive": "innovative",
    "disruptor": "innovator",
}


def _compile_patterns(
    replacements: dict[str, str],
) -> list[tuple[re.Pattern[str], str]]:
    sorted_pairs = sorted(replacements.items(), key=lambda kv: -len(kv[0]))
    return [
        (re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE), replacement)
        for phrase, replacement in sorted_pairs
    ]


class LocalPhraseFilter(IDraftPostProcessor):
    def __init__(self, extra_replacements: dict[str, str] | None = None) -> None:
        merged = {**_REPLACEMENTS, **(extra_replacements or {})}
        self._patterns = _compile_patterns(merged)

    def filter_text(self, text: str) -> str:
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        text = re.sub(r" {2,}", " ", text).strip()
        return text

    def process(self, draft: TailoredResumeDraft) -> TailoredResumeDraft:
        result = copy.deepcopy(draft)
        replaced = 0

        result.summary = self.filter_text(result.summary)

        for exp in result.experiences:
            for bullet in exp.bullets:
                cleaned = self.filter_text(bullet.text)
                if cleaned != bullet.text:
                    replaced += 1
                bullet.text = cleaned

        for proj in result.projects:
            proj.description = self.filter_text(proj.description)
            for bullet in proj.bullets:
                cleaned = self.filter_text(bullet.text)
                if cleaned != bullet.text:
                    replaced += 1
                bullet.text = cleaned

        logger.info("phrase_filter | replaced phrases in %d bullets", replaced)
        return result
