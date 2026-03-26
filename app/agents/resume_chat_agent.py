import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_factory import get_model_factory

from app.models.data_models import (
    ChatMessage,
    ChatScope,
    JobDescription,
    ResumeChatRequest,
    ResumeChatResponse,
    ResumePatch,
    TailoredExperience,
    TailoredProject,
    TailoredResumeDraft,
)

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


def _extract_section(draft: TailoredResumeDraft, path: str) -> tuple[str, Any]:
    if path == "summary":
        return "summary", draft.summary
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

class OllamaResumeChatAgent:
    def __init__(self) -> None:
        factory = get_model_factory()
        self._llm = factory.build("resume_chat_json")
        self._llm_stream = factory.build("resume_chat_stream")
        self._intent_tpl = _load("chat_intent.txt")
        self._local_tpl = _load("chat_local_patch.txt")
        self._global_tpl = _load("chat_global_feedback.txt")

    # ── non-streaming fallback ──────────────────────────────────
    async def chat(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription] = None,
    ) -> ResumeChatResponse:
        intent = await self._route_intent(request.message, request.scope)
        logger.info("chat | intent=%s scope=%s", intent, request.scope.path if request.scope else None)

        if intent == "local_patch" and request.scope:
            return await self._handle_local_patch(request, jd)
        elif intent == "global_feedback":
            return await self._handle_global_feedback(request, jd)
        else:
            return await self._handle_question(request)

    # ── streaming entry point ───────────────────────────────────

    async def stream_chat(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription] = None,
    ) -> AsyncGenerator[str, None]:
        intent = await self._route_intent(request.message, request.scope)
        logger.info("stream_chat | intent=%s", intent)

        yield _sse("intent", {"value": intent})

        if intent == "local_patch" and request.scope:
            async for event in self._stream_local_patch(request, jd):
                yield event
        elif intent == "global_feedback":
            async for event in self._stream_global_feedback(request, jd):
                yield event
        else:
            async for event in self._stream_question(request):
                yield event

    # ── streaming handlers ──────────────────────────────────────

    async def _stream_local_patch(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> AsyncGenerator[str, None]:
        assert request.scope is not None
        section_type, section = _extract_section(request.draft, request.scope.path)
        section_json = (
            section.model_dump_json() if hasattr(section, "model_dump_json") else json.dumps(section)
        )
        jd_keywords = jd.core_keywords if jd else []

        # Step 1 — stream the reply text using non-JSON LLM
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

        # Step 2 — generate the JSON patch
        patch_prompt = self._local_tpl.format(
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
            instruction=request.message,
        )
        try:
            resp = await self._llm.ainvoke([HumanMessage(content=patch_prompt)])
            data = _parse_json(str(resp.content))
            updated = data.get("updated_section")
            diff_summary: str = data.get("diff_summary") or reply_text

            if updated is not None:
                _apply_patch_value(request.draft, request.scope.path, updated)
                patch = ResumePatch(
                    path=request.scope.path,
                    updated_value=updated,
                    diff_summary=diff_summary,
                )
                yield _sse("patch", patch.model_dump())
        except Exception as exc:
            logger.warning("stream_local_patch | patch generation failed: %s", exc)

        yield _sse("done", {"reply": reply_text})

    async def _stream_global_feedback(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> AsyncGenerator[str, None]:
        stream_prompt = (
            f"You are a professional resume coach.\n"
            f"User concern: {request.message}\n\n"
            f"Resume summary section: {request.draft.summary[:400]}\n\n"
            f"Provide 2-4 sentences of specific, actionable feedback addressing the user's concern."
        )
        reply_text = ""
        async for chunk in self._llm_stream.astream([HumanMessage(content=stream_prompt)]):
            token: str = _extract_token(chunk.content)
            if token:
                reply_text += token
                yield _sse("token", {"content": token})

        # Attempt patch generation
        patch_prompt = self._global_tpl.format(
            jd_json=jd.model_dump_json() if jd else "{}",
            draft_json=request.draft.model_dump_json(),
            message=request.message,
        )
        try:
            resp = await self._llm.ainvoke([HumanMessage(content=patch_prompt)])
            data = _parse_json(str(resp.content))
            patch_data: Optional[dict] = data.get("patch")
            diff_summary_raw = data.get("diff_summary")

            if patch_data and patch_data.get("path") and patch_data.get("updated_value") is not None:
                patch = ResumePatch(
                    path=patch_data["path"],
                    updated_value=patch_data["updated_value"],
                    diff_summary=diff_summary_raw or "Updated based on your feedback.",
                )
                yield _sse("patch", patch.model_dump())
        except Exception as exc:
            logger.warning("stream_global_feedback | patch generation failed: %s", exc)

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

    # ── intent routing ──────────────────────────────────────────

    async def _route_intent(self, message: str, scope: Optional[ChatScope]) -> str:
        scope_context = f"{scope.label} ({scope.path})" if scope else "none"
        prompt = self._intent_tpl.format(scope_context=scope_context, message=message)
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        try:
            data = _parse_json(str(resp.content))
            return data.get("intent", "question")
        except Exception:
            logger.warning("chat | intent parse failed, defaulting")
            return "local_patch" if scope else "question"

    # ── non-streaming handlers (kept for fallback) ──────────────

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
        jd_keywords = jd.core_keywords if jd else []

        prompt = self._local_tpl.format(
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
            instruction=request.message,
        )
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(str(resp.content))

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

    async def _handle_global_feedback(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> ResumeChatResponse:
        prompt = self._global_tpl.format(
            jd_json=jd.model_dump_json() if jd else "{}",
            draft_json=request.draft.model_dump_json(),
            message=request.message,
        )
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(str(resp.content))

        reply_text: str = data.get("reply", "Here is my analysis.")
        diff_summary_raw = data.get("diff_summary")
        patch_data: Optional[dict] = data.get("patch")

        patch: Optional[ResumePatch] = None
        if patch_data and patch_data.get("path") and patch_data.get("updated_value") is not None:
            patch = ResumePatch(
                path=patch_data["path"],
                updated_value=patch_data["updated_value"],
                diff_summary=diff_summary_raw or "Updated based on your feedback.",
            )

        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text, patch=patch)
        return ResumeChatResponse(message=msg, patch=patch)

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
        reply_text = str(resp.content).strip()
        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text)
        return ResumeChatResponse(message=msg, patch=None)
