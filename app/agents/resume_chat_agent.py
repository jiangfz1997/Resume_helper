import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage

from app.core.model_factory import get_model_factory
from app.models.data_models import (
    ChatMessage,
    JobDescription,
    MasterProfile,
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
        if isinstance(updated, dict):
            updated = updated.get("content") or updated.get("text") or str(updated)
        draft.summary = str(updated)
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


def _build_patch_prompt(
    local_tpl: str,
    bullet_tpl: str,
    section_type: str,
    section: Any,
    jd_keywords: list[str],
    instruction: str,
) -> tuple[str, bool]:
    """Return (prompt, is_bullet)."""
    is_bullet = section_type == "bullet"
    if is_bullet:
        prompt = bullet_tpl.format(
            section_json=section["full_item"].model_dump_json(),
            bullet_index=section["bullet_index"],
            bullet_text=section["bullet_text"],
            jd_keywords=", ".join(jd_keywords),
            instruction=instruction,
        )
    else:
        section_json = (
            section.model_dump_json() if hasattr(section, "model_dump_json") else json.dumps(section)
        )
        prompt = local_tpl.format(
            section_type=section_type,
            section_json=section_json,
            jd_keywords=", ".join(jd_keywords),
            instruction=instruction,
        )
    return prompt, is_bullet


class OllamaResumeChatAgent:
    def __init__(self) -> None:
        factory = get_model_factory()
        self._llm = factory.build("resume_chat_json")
        self._llm_stream = factory.build("resume_chat_stream")
        self._local_tpl = _load("chat_local_patch.txt")
        self._bullet_tpl = _load("chat_bullet_patch.txt")

    # ── streaming entry point ───────────────────────────────────

    async def stream_chat(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription] = None,
        profile: Optional[MasterProfile] = None,
    ) -> AsyncGenerator[str, None]:
        if request.scope:
            async for event in self._stream_local_patch(request, jd):
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
            return await self._handle_local_patch(request, jd)
        return await self._handle_question(request)

    # ── streaming handlers ──────────────────────────────────────

    async def _stream_local_patch(
        self,
        request: ResumeChatRequest,
        jd: Optional[JobDescription],
    ) -> AsyncGenerator[str, None]:
        assert request.scope is not None
        reply_text = ""
        try:
            section_type, section = _extract_section(request.draft, request.scope.path)
            jd_keywords = jd.tech_keywords if jd else []
            prompt, is_bullet = _build_patch_prompt(
                self._local_tpl, self._bullet_tpl,
                section_type, section, jd_keywords, request.message,
            )

            resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
            data = _parse_json(_extract_token(resp.content))
            logger.debug("stream_local_patch | parsed data keys=%s", list(data.keys()))

            reply_text = data.get("reply", "")
            diff_summary: str = data.get("diff_summary", reply_text)
            updated = data.get("updated_bullet") if is_bullet else data.get("updated_section")

            for char in reply_text:
                yield _sse("token", {"content": char})

            if updated is not None:
                _apply_patch_value(request.draft, request.scope.path, updated)
                patch = ResumePatch(
                    path=request.scope.path,
                    updated_value=updated,
                    diff_summary=diff_summary,
                )
                yield _sse("patch", patch.model_dump())
            else:
                logger.warning("stream_local_patch | updated field missing from LLM response")
                yield _sse("token", {"content": "\n\n_(Could not apply patch — please edit manually.)_"})

        except Exception as exc:
            logger.warning("stream_local_patch | failed: %s", exc)
            yield _sse("token", {"content": "Sorry, something went wrong. Please try again."})

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
            token = _extract_token(chunk.content)
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
        jd_keywords = jd.tech_keywords if jd else []
        prompt, is_bullet = _build_patch_prompt(
            self._local_tpl, self._bullet_tpl,
            section_type, section, jd_keywords, request.message,
        )

        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        data = _parse_json(_extract_token(resp.content))

        reply_text: str = data.get("reply", "Updated the section per your instruction.")
        diff_summary: str = data.get("diff_summary", reply_text)
        updated = data.get("updated_bullet") if is_bullet else data.get("updated_section")

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

    async def _handle_question(self, request: ResumeChatRequest) -> ResumeChatResponse:
        history_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in request.history[-6:]
        )
        prompt = (
            f"You are a helpful resume assistant. Answer the user's question concisely "
            f"based on the resume draft and conversation context. Do not fabricate information.\n\n"
            f"Resume summary: {request.draft.summary[:300]}\n\n"
            f"Recent conversation:\n{history_text}\n\n"
            f"User question: {request.message}"
        )
        resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
        reply_text = _extract_token(resp.content).strip()
        msg = ChatMessage(id=uuid.uuid4(), role="assistant", content=reply_text)
        return ResumeChatResponse(message=msg, patch=None)
