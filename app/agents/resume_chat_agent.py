import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.diagnostic_analyzer import DiagnosticAnalyzer
from app.core.model_factory import get_model_factory
from app.models.data_models import (
    ChatMessage,
    ChatScope,
    DiagnosticTask,
    IntentResult,
    JobDescription,
    MasterProfile,
    ResumeChatRequest,
    ResumeChatResponse,
    ResumePatch,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
)
from app.services import tier1_checker

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent.parent / "prompts"


def _load(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def _extract_token(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return ""


_BULLET_PATH_RE = re.compile(r"^(experiences|projects)\[(\d+)\]\.bullets\[(\d+)\]$")


def _extract_section(draft: TailoredResumeDraft, path: str) -> tuple[str, Any]:
    if path == "summary":
        return "summary", draft.summary
    m_b = _BULLET_PATH_RE.match(path)
    if m_b:
        field, item_idx, bullet_idx = m_b.group(1), int(m_b.group(2)), int(m_b.group(3))
        item = getattr(draft, field)[item_idx]
        return "bullet", {
            "full_item": item,
            "bullet_index": bullet_idx,
            "bullet_text": item.bullets[bullet_idx].text,
        }
    m = re.match(r"^(experiences|projects|education|skills)\[(\d+)\]$", path)
    if not m:
        raise ValueError(f"Unsupported scope path: {path}")
    field, idx = m.group(1), int(m.group(2))
    items = getattr(draft, field)
    if idx >= len(items):
        raise ValueError(f"Index {idx} out of range for {field}")
    return field, items[idx]


def _apply_patch_value(draft: TailoredResumeDraft, path: str, updated: Any) -> None:
    if path == "summary":
        draft.summary = updated
        return
    m_b = _BULLET_PATH_RE.match(path)
    if m_b:
        field, item_idx, bullet_idx = m_b.group(1), int(m_b.group(2)), int(m_b.group(3))
        getattr(draft, field)[item_idx].bullets[bullet_idx].text = str(updated)
        return
    m = re.match(r"^(experiences|projects|education|skills)\[(\d+)\]$", path)
    if not m:
        return
    field, idx = m.group(1), int(m.group(2))
    items = getattr(draft, field)
    if field == "experiences":
        items[idx] = TailoredExperience(**updated) if isinstance(updated, dict) else updated
    elif field == "projects":
        items[idx] = TailoredProject(**updated) if isinstance(updated, dict) else updated
    else:
        items[idx] = updated


def _section_text(item: Any) -> str:
    """Flatten a TailoredExperience or TailoredProject to a searchable string."""
    parts: list[str] = []
    if hasattr(item, "title"):
        parts.append(item.title)
    if hasattr(item, "company"):
        parts.append(item.company)
    if hasattr(item, "name"):
        parts.append(item.name)
    if hasattr(item, "description"):
        parts.append(item.description)
    if hasattr(item, "tech_stack"):
        parts.extend(item.tech_stack)
    if hasattr(item, "bullets"):
        parts.extend(b.text for b in item.bullets)
    return " ".join(parts).lower()


def _find_best_section_for_keyword(
    keyword: str,
    draft: TailoredResumeDraft,
) -> tuple[str, int] | None:
    """Return (section_type, index) of the section most likely to accept the keyword."""
    kw = keyword.lower()
    best_field: str | None = None
    best_idx: int = 0
    best_score: int = -1

    for field in ("experiences", "projects"):
        for idx, item in enumerate(getattr(draft, field)):
            text = _section_text(item)
            # exact keyword already present — skip
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                continue
            # score = number of keyword-adjacent tech terms present in section text
            score = sum(1 for w in text.split() if len(w) > 3 and w in text)
            if score > best_score:
                best_score = score
                best_field = field
                best_idx = idx

    if best_field is None:
        return None
    return best_field, best_idx


def _format_diagnose_reply(tasks: list[DiagnosticTask]) -> str:
    if not tasks:
        return "No significant issues found. Your resume looks solid against the JD."
    lines: list[str] = []
    for task in tasks:
        tier_label = {"tier1": "Required", "tier2": "Suggested", "tier3": "Polish"}.get(
            task.tier.value, task.tier.value
        )
        lines.append(f"[{tier_label}] **{task.title}**\n{task.description}")
    return "\n\n".join(lines)


class OllamaResumeChatAgent:
    def __init__(self) -> None:
        factory = get_model_factory()
        self._llm = factory.build("resume_chat_json")
        self._llm_stream = factory.build("resume_chat_stream")
        self._router_model = factory.build_chat_model("chat_intent_router")
        self._diagnostic_analyzer = DiagnosticAnalyzer()

        self._intent_router_tpl = _load("chat_intent_router.txt")
        self._local_tpl = _load("chat_local_patch.txt")
        self._bullet_tpl = _load("chat_bullet_patch.txt")
        self._keyword_inject_tpl = _load("chat_keyword_inject.txt")

    # ── streaming entry point ───────────────────────────────────

    async def stream_chat(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription] = None,
        profile: Optional[MasterProfile] = None,
    ) -> AsyncGenerator[str, None]:
        if request.scope:
            intent_result = IntentResult(intent="local_patch")
        else:
            intent_result = await self._route_intent(request.message, request.scope)

        logger.info("stream_chat | intent=%s keyword=%s", intent_result.intent, intent_result.keyword)
        yield _sse("intent", {"value": intent_result.intent})

        if intent_result.intent == "local_patch" and request.scope:
            async for event in self._stream_local_patch(request, jd):
                yield event
        elif intent_result.intent == "keyword_inject":
            async for event in self._stream_keyword_inject(request, jd, intent_result.keyword or ""):
                yield event
        elif intent_result.intent == "full_diagnose":
            async for event in self._stream_full_diagnose(request, jd, profile):
                yield event
        else:
            async for event in self._stream_question(request):
                yield event

    # ── non-streaming fallback ──────────────────────────────────

    async def chat(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription] = None,
        profile: Optional[MasterProfile] = None,
    ) -> ResumeChatResponse:
        if request.scope:
            intent_result = IntentResult(intent="local_patch")
        else:
            intent_result = await self._route_intent(request.message, request.scope)

        if intent_result.intent == "local_patch" and request.scope:
            return await self._handle_local_patch(request, jd)
        elif intent_result.intent == "keyword_inject":
            return await self._handle_keyword_inject(request, jd, intent_result.keyword or "")
        elif intent_result.intent == "full_diagnose":
            return await self._handle_full_diagnose(request, jd, profile)
        else:
            return await self._handle_question(request)

    # ── intent routing ──────────────────────────────────────────

    async def _route_intent(self, message: str, scope: Optional[ChatScope]) -> IntentResult:
        scope_context = f"{scope.label} ({scope.path})" if scope else "none"
        prompt_text = self._intent_router_tpl.format(
            scope_context=scope_context, message=message
        )
        structured = self._router_model.with_structured_output(IntentResult)
        try:
            result = await structured.ainvoke([HumanMessage(content=prompt_text)])
            return result  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("intent_router | failed (%s), defaulting to question", exc)
            return IntentResult(intent="question")

    # ── streaming handlers ──────────────────────────────────────

    async def _stream_local_patch(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> AsyncGenerator[str, None]:
        assert request.scope is not None
        section_type, section = _extract_section(request.draft, request.scope.path)
        jd_keywords = jd.tech_keywords if jd else []
        is_bullet = section_type == "bullet"

        if is_bullet:
            full_item = section["full_item"]
            bullet_index: int = section["bullet_index"]
            bullet_text: str = section["bullet_text"]
            context_json = full_item.model_dump_json()
            stream_prompt = (
                f"You are a professional resume editor.\n"
                f"The user wants to improve a specific bullet point.\n"
                f"Bullet: \"{bullet_text}\"\n"
                f"JD keywords: {', '.join(jd_keywords)}\n"
                f"User instruction: {request.message}\n\n"
                f"In 1-2 sentences, explain what change you will make and why. "
                f"If the instruction is vague, describe the most impactful improvement you inferred."
            )
        else:
            section_json = (
                section.model_dump_json() if hasattr(section, "model_dump_json") else json.dumps(section)
            )
            stream_prompt = (
                f"You are a professional resume editor.\n"
                f"Section type: {section_type}\n"
                f"Current section: {section_json}\n"
                f"JD keywords: {', '.join(jd_keywords)}\n"
                f"User instruction: {request.message}\n\n"
                f"In 1-2 sentences, explain to the user what changes you will make to this section "
                f"and why. Be conversational and specific."
            )

        reply_text = ""
        async for chunk in self._llm_stream.astream([HumanMessage(content=stream_prompt)]):
            token: str = _extract_token(chunk.content)
            if token:
                reply_text += token
                yield _sse("token", {"content": token})

        if is_bullet:
            patch_prompt = self._bullet_tpl.format(
                section_json=context_json,
                bullet_index=bullet_index,
                bullet_text=bullet_text,
                jd_keywords=", ".join(jd_keywords),
                instruction=request.message,
            )
        else:
            patch_prompt = self._local_tpl.format(
                section_type=section_type,
                section_json=section_json,
                jd_keywords=", ".join(jd_keywords),
                instruction=request.message,
            )

        try:
            resp = await self._llm.ainvoke([HumanMessage(content=patch_prompt)])
            raw_resp = _extract_token(resp.content)
            logger.debug("stream_local_patch | raw_patch_resp=%.500s", raw_resp)
            data = _parse_json(raw_resp)

            updated = data.get("updated_bullet") if is_bullet else data.get("updated_section")
            diff_summary: str = data.get("diff_summary") or reply_text

            if updated is not None:
                _apply_patch_value(request.draft, request.scope.path, updated)
                patch = ResumePatch(
                    path=request.scope.path,
                    updated_value=updated,
                    diff_summary=diff_summary,
                )
                yield _sse("patch", patch.model_dump())
            else:
                logger.warning("stream_local_patch | updated field missing from response")
                yield _sse("token", {"content": "\n\n_(Could not apply patch automatically — please edit manually.)_"})
        except Exception as exc:
            logger.warning("stream_local_patch | patch generation failed: %s", exc)
            yield _sse("token", {"content": "\n\n_(Patch failed — please apply the changes above manually.)_"})

        yield _sse("done", {"reply": reply_text})

    async def _stream_keyword_inject(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
        keyword: str,
    ) -> AsyncGenerator[str, None]:
        if not keyword:
            yield _sse("token", {"content": "I couldn't identify which keyword you want to add. Please name the specific technology or skill."})
            yield _sse("done", {"reply": ""})
            return

        target = _find_best_section_for_keyword(keyword, request.draft)
        if target is None:
            msg = f"The keyword **{keyword}** already appears in your resume, or no suitable section was found to place it naturally."
            yield _sse("token", {"content": msg})
            yield _sse("done", {"reply": msg})
            return

        field, idx = target
        items = getattr(request.draft, field)
        section = items[idx]
        section_json = section.model_dump_json()
        section_type = "experience" if field == "experiences" else "project"
        jd_keywords = jd.tech_keywords if jd else []

        stream_prompt = (
            f"You are a professional resume editor.\n"
            f"The user wants to incorporate '{keyword}' into their {section_type} "
            f"'{getattr(section, 'company', None) or getattr(section, 'name', '')}'.\n"
            f"In 1-2 sentences, explain where and how you will fit it in naturally."
        )

        reply_text = ""
        async for chunk in self._llm_stream.astream([HumanMessage(content=stream_prompt)]):
            token: str = _extract_token(chunk.content)
            if token:
                reply_text += token
                yield _sse("token", {"content": token})

        patch_prompt = self._keyword_inject_tpl.format(
            keyword=keyword,
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
        )

        path = f"{field}[{idx}]"
        try:
            resp = await self._llm.ainvoke([HumanMessage(content=patch_prompt)])
            data = _parse_json(_extract_token(resp.content))
            updated = data.get("updated_section")
            diff_summary: str = data.get("diff_summary") or reply_text

            if updated is not None:
                _apply_patch_value(request.draft, path, updated)
                patch = ResumePatch(
                    path=path,
                    updated_value=updated,
                    diff_summary=diff_summary,
                )
                yield _sse("patch", patch.model_dump())
            else:
                yield _sse("token", {"content": "\n\n_(Could not apply patch automatically — please edit manually.)_"})
        except Exception as exc:
            logger.warning("stream_keyword_inject | patch generation failed: %s", exc)
            yield _sse("token", {"content": "\n\n_(Patch failed — please apply the changes above manually.)_"})

        yield _sse("done", {"reply": reply_text})

    async def _stream_full_diagnose(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
        profile: Optional[MasterProfile],
    ) -> AsyncGenerator[str, None]:
        yield _sse("token", {"content": "Analyzing your resume against the job description...\n\n"})

        tier1_tasks: list[DiagnosticTask] = []
        if profile is not None:
            tier1_tasks = tier1_checker.run(profile, request.draft)

        llm_tasks: list[DiagnosticTask] = []
        if jd is not None:
            try:
                llm_tasks = await self._diagnostic_analyzer.analyze(request.draft, jd)
            except Exception as exc:
                logger.warning("stream_full_diagnose | DiagnosticAnalyzer failed: %s", exc)

        all_tasks = tier1_tasks + llm_tasks
        top_tasks = all_tasks[:5]

        reply_text = _format_diagnose_reply(top_tasks)
        yield _sse("token", {"content": reply_text})

        # Emit patch for first replaceable tier3 task, if any
        replaceable = next((t for t in top_tasks if t.replaceable and t.original_text and t.suggested_text), None)
        if replaceable and replaceable.section:
            m = re.match(r"^(experiences|projects)\[(\d+)\]", replaceable.section)
            if m:
                path = f"{m.group(1)}[{m.group(2)}]"
                try:
                    field, idx_str = m.group(1), int(m.group(2))
                    items = getattr(request.draft, field)
                    item = items[idx_str]
                    for b_idx, bullet in enumerate(item.bullets):
                        if bullet.text == replaceable.original_text:
                            bullet_path = f"{path}.bullets[{b_idx}]"
                            _apply_patch_value(request.draft, bullet_path, replaceable.suggested_text)
                            patch = ResumePatch(
                                path=bullet_path,
                                updated_value=replaceable.suggested_text,
                                diff_summary=replaceable.title,
                            )
                            yield _sse("patch", patch.model_dump())
                            break
                except Exception as exc:
                    logger.warning("stream_full_diagnose | auto-patch failed: %s", exc)

        yield _sse("done", {"reply": reply_text})

    async def _stream_question(
        self,
        request: ResumeChatRequest,
    ) -> AsyncGenerator[str, None]:
        history_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in request.history[-6:]
        )
        prompt = (
            f"You are a helpful resume assistant. Answer the user's question concisely.\n\n"
            f"Resume summary: {request.draft.summary[:300]}\n\n"
            f"Recent conversation:\n{history_text}\n\n"
            f"User question: {request.message}"
        )
        reply_text = ""
        async for chunk in self._llm_stream.astream([HumanMessage(content=prompt)]):
            token: str = _extract_token(chunk.content)
            if token:
                reply_text += token
                yield _sse("token", {"content": token})

        yield _sse("done", {"reply": reply_text})

    # ── non-streaming handlers ──────────────────────────────────

    async def _handle_local_patch(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> ResumeChatResponse:
        assert request.scope is not None
        section_type, section = _extract_section(request.draft, request.scope.path)
        section_json = (
            section.model_dump_json() if hasattr(section, "model_dump_json") else json.dumps(section)
        )
        jd_keywords = jd.tech_keywords if jd else []

        prompt = self._local_tpl.format(
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
            instruction=request.message,
        )
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(_extract_token(resp.content))

        reply_text: str = data.get("reply", "Updated the section per your instruction.")
        diff_summary: str = data.get("diff_summary") or reply_text
        updated = data.get("updated_section")

        patch: Optional[ResumePatch] = None
        if updated is not None:
            _apply_patch_value(request.draft, request.scope.path, updated)
            patch = ResumePatch(
                path=request.scope.path,
                updated_value=updated,
                diff_summary=diff_summary,
            )

        msg = ChatMessage(
            id=uuid.uuid4(),
            role="assistant",
            content=reply_text,
            scope=request.scope,
            patch=patch,
        )
        return ResumeChatResponse(message=msg, patch=patch)

    async def _handle_keyword_inject(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
        keyword: str,
    ) -> ResumeChatResponse:
        if not keyword:
            msg = ChatMessage(id=uuid.uuid4(), role="assistant", content="Please name the specific technology or skill you want to add.")
            return ResumeChatResponse(message=msg, patch=None)

        target = _find_best_section_for_keyword(keyword, request.draft)
        if target is None:
            reply = f"The keyword '{keyword}' already appears in your resume, or no suitable section was found."
            msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply)
            return ResumeChatResponse(message=msg, patch=None)

        field, idx = target
        section = getattr(request.draft, field)[idx]
        section_json = section.model_dump_json()
        section_type = "experience" if field == "experiences" else "project"
        jd_keywords = jd.tech_keywords if jd else []

        prompt = self._keyword_inject_tpl.format(
            keyword=keyword,
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
        )
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(_extract_token(resp.content))

        reply_text: str = data.get("reply", f"Injected '{keyword}' into the section.")
        diff_summary: str = data.get("diff_summary") or reply_text
        updated = data.get("updated_section")

        path = f"{field}[{idx}]"
        patch: Optional[ResumePatch] = None
        if updated is not None:
            _apply_patch_value(request.draft, path, updated)
            patch = ResumePatch(path=path, updated_value=updated, diff_summary=diff_summary)

        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text, patch=patch)
        return ResumeChatResponse(message=msg, patch=patch)

    async def _handle_full_diagnose(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
        profile: Optional[MasterProfile],
    ) -> ResumeChatResponse:
        tier1_tasks: list[DiagnosticTask] = []
        if profile is not None:
            tier1_tasks = tier1_checker.run(profile, request.draft)

        llm_tasks: list[DiagnosticTask] = []
        if jd is not None:
            try:
                llm_tasks = await self._diagnostic_analyzer.analyze(request.draft, jd)
            except Exception as exc:
                logger.warning("handle_full_diagnose | DiagnosticAnalyzer failed: %s", exc)

        all_tasks = tier1_tasks + llm_tasks
        reply_text = _format_diagnose_reply(all_tasks[:5])
        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text)
        return ResumeChatResponse(message=msg, patch=None)

    async def _handle_question(self, request: ResumeChatRequest) -> ResumeChatResponse:
        system = SystemMessage(content=(
            "You are a helpful resume assistant. Answer the user's question concisely "
            "based on the resume draft and conversation context. Do not fabricate information."
        ))
        history_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in request.history[-6:]
        )
        user_msg = HumanMessage(content=(
            f"Resume draft summary section: {request.draft.summary[:300]}\n\n"
            f"Recent conversation:\n{history_text}\n\n"
            f"User question: {request.message}"
        ))
        resp = await self._llm.ainvoke([system, user_msg])
        reply_text = _extract_token(resp.content).strip()
        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text)
        return ResumeChatResponse(message=msg, patch=None)
