import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.models.data_models import (
    DiagnosticTask,
    DiagnosticTier,
    JobDescription,
    TailoredResumeDraft,
)

logger = logging.getLogger(__name__)


def _fix_literal_newlines(text: str) -> str:
    """Replace literal control characters inside JSON string values.

    Uses a character-level state machine to correctly track string context,
    handling escaped quotes and backslash sequences properly.
    """
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
        elif ch == "\\":
            result.append(ch)
            escaped = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _extract_task_objects(raw: str) -> list[dict]:
    """Extract individual task dicts from raw LLM output robustly.

    Uses brace-matching to pull out each complete ``{...}`` task object from
    the ``"tasks"`` array, even when the surrounding JSON is truncated or
    contains literal newlines in string values.  Incomplete (unclosed) task
    objects near the end of the output are silently skipped.
    """
    tasks_marker = raw.find('"tasks"')
    if tasks_marker == -1:
        return []
    bracket = raw.find("[", tasks_marker)
    if bracket == -1:
        return []

    results: list[dict] = []
    i = bracket + 1
    while i < len(raw):
        # Skip whitespace and commas between task objects
        while i < len(raw) and raw[i] in " \t\n\r,":
            i += 1
        if i >= len(raw) or raw[i] != "{":
            break

        # Walk forward with brace/string tracking to find matching "}"
        depth = 0
        j = i
        in_str = False
        esc = False
        while j < len(raw):
            ch = raw[j]
            if esc:
                esc = False
            elif ch == "\\" and in_str:
                esc = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        task_chunk = _fix_literal_newlines(raw[i : j + 1])
                        try:
                            obj = json.loads(task_chunk)
                            results.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            j += 1
        else:
            # Reached end of raw without finding matching "}" — task truncated
            break

    return results

_prompt_text = (
    Path(__file__).parent.parent / "prompts" / "diagnostic_analyzer.txt"
).read_text(encoding="utf-8")


def _draft_for_llm(draft: TailoredResumeDraft) -> str:
    """Serialize draft for LLM input, stripping fields that add noise without value."""
    data = draft.model_dump()
    data["skills"] = [s["name"] for s in data["skills"]]
    for key in ("education", "contact_info", "template_id", "template_source"):
        data.pop(key, None)
    return json.dumps(data)


_FALLBACK_MAX_TOKENS = 4096


def _is_deadline_exceeded(exc: BaseException) -> bool:
    return "DEADLINE_EXCEEDED" in str(exc) or "504" in str(exc)


class DiagnosticAnalyzer:
    def __init__(self) -> None:
        factory = get_model_factory()
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | factory.build("diagnostic_analyzer") | StrOutputParser()
        self._chain_fallback = (
            prompt | factory.build("diagnostic_analyzer", max_tokens_override=_FALLBACK_MAX_TOKENS) | StrOutputParser()
        )

    async def analyze(
        self,
        draft: TailoredResumeDraft,
        jd: JobDescription,
    ) -> list[DiagnosticTask]:
        invoke_input = {
            "draft_json": _draft_for_llm(draft),
            "jd_json": jd.model_dump_json(indent=2),
        }
        try:
            raw = await self._chain.ainvoke(invoke_input)
            logger.debug("diagnostic_analyzer | primary | raw_len=%d | preview=%.300s", len(raw), raw)
        except Exception as exc:
            if not _is_deadline_exceeded(exc):
                raise
            logger.warning(
                "diagnostic_analyzer | primary chain DEADLINE_EXCEEDED, retrying with fallback (max_tokens=%d)",
                _FALLBACK_MAX_TOKENS,
            )
            raw = await self._chain_fallback.ainvoke(invoke_input)
            logger.debug("diagnostic_analyzer | fallback | raw_len=%d | preview=%.300s", len(raw), raw)

        # Fast path: try parsing the whole JSON block at once
        tasks_raw: list[dict] = []
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            chunk = raw[start:end]
            fixed = _fix_literal_newlines(chunk)
            data = json.loads(fixed)
            tasks_raw = data.get("tasks", [])
        except (ValueError, json.JSONDecodeError) as exc:
            # Slow path: output may be truncated — extract task objects individually
            logger.warning("diagnostic_analyzer | whole-JSON parse failed (%s), falling back to per-task extraction", exc)
            tasks_raw = _extract_task_objects(raw)

        tasks: list[DiagnosticTask] = []
        for item in tasks_raw:
            try:
                task = DiagnosticTask.model_validate(item)
                if task.tier not in (DiagnosticTier.tier2, DiagnosticTier.tier3):
                    logger.warning("diagnostic_analyzer | unexpected tier=%s, skipping", task.tier)
                    continue
                tasks.append(task)
            except Exception as exc:
                logger.warning("diagnostic_analyzer | invalid task item, skipping: %s", exc)

        logger.info("diagnostic_analyzer | returned %d tasks", len(tasks))
        return tasks
