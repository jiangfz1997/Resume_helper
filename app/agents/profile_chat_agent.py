import json
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage

from app.core.model_factory import get_model_factory
from app.models.data_models import ProfileChatRequest, ResumePatch

logger = logging.getLogger(__name__)


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


def _parse_json(raw: str) -> dict:
    import re
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _build_path(section_type: str, section_index: int | None) -> str:
    if section_index is None:
        return section_type
    return f"{section_type}[{section_index}]"


class OllamaProfileChatAgent:
    def __init__(self) -> None:
        factory = get_model_factory()
        self._llm_json = factory.build("resume_chat_json")
        self._llm_stream = factory.build("resume_chat_stream")

    async def stream_chat(
        self,
        request: ProfileChatRequest,
    ) -> AsyncGenerator[str, None]:
        section_json = json.dumps(request.section_data, ensure_ascii=False)
        path = _build_path(request.section_type, request.section_index)

        stream_prompt = (
            f"You are a professional resume editor helping improve a profile section.\n"
            f"Section type: {request.section_type}\n"
            f"Current content:\n{section_json}\n\n"
            f"User instruction: {request.message}\n\n"
            f"In 1-2 sentences, explain what specific changes you will make and why. "
            f"Be concise and professional."
        )

        reply_text = ""
        async for chunk in self._llm_stream.astream([HumanMessage(content=stream_prompt)]):
            token = _extract_token(chunk.content)
            if token:
                reply_text += token
                yield _sse("token", {"content": token})

        patch_prompt = self._build_patch_prompt(
            section_type=request.section_type,
            section_json=section_json,
            instruction=request.message,
        )
        try:
            resp = await self._llm_json.ainvoke([HumanMessage(content=patch_prompt)])
            data = _parse_json(str(resp.content))
            updated: Any = data.get("updated_section")
            diff_summary: str = data.get("diff_summary") or reply_text

            if updated is not None:
                patch = ResumePatch(
                    path=path,
                    updated_value=updated,
                    diff_summary=diff_summary,
                )
                yield _sse("patch", patch.model_dump())
        except Exception as exc:
            logger.warning("profile_chat | patch generation failed: %s", exc)

        yield _sse("done", {"reply": reply_text})

    def _build_patch_prompt(
        self,
        section_type: str,
        section_json: str,
        instruction: str,
    ) -> str:
        type_hints: dict[str, str] = {
            "summary": 'Return updated_section as a plain string.',
            "work_experiences": (
                'Return updated_section as a JSON object matching: '
                '{"company": str, "title": str, "start_date": str, "end_date": str|null, "description": [str]}'
            ),
            "educations": (
                'Return updated_section as a JSON object matching: '
                '{"institution": str, "degree": str, "field_of_study": str, '
                '"start_date": str, "end_date": str|null, "gpa": str|null}'
            ),
            "projects": (
                'Return updated_section as a JSON object matching: '
                '{"name": str, "description": str, "bullets": [str], "tech_stack": [str], "url": str|null}'
            ),
            "skills": (
                'Return updated_section as a JSON array of objects matching: '
                '[{"category": str, "name": str, "proficiency": "expert"|"intermediate"|"beginner"}]'
            ),
        }
        hint = type_hints.get(section_type, "Return updated_section with the same schema as the input.")

        return (
            f"You are a professional resume editor. Apply the user instruction to the profile section below.\n\n"
            f"Section type: {section_type}\n"
            f"Current content:\n{section_json}\n\n"
            f"User instruction: {instruction}\n\n"
            f"{hint}\n\n"
            f"Respond ONLY with valid JSON in this exact format:\n"
            f'{{"updated_section": <updated content>, "diff_summary": "<one sentence summary of changes>"}}\n'
            f"Do not include any explanation outside the JSON."
        )
