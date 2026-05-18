import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_chat_agent,
    get_chat_repo,
    get_current_user_id,
    get_profile_repo,
    get_session_repo,
)
from app.agents.resume_chat_agent import OllamaResumeChatAgent
from app.models.data_models import (
    ChatMessage,
    JobDescription,
    MasterProfile,
    ResumeChatRequest,
    ResumeChatResponse,
    ResumePatch,
)
from app.repositories.chat_repository import ChatRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.session_repository import ResumeSessionRepository

router = APIRouter(prefix="/resume/chat", tags=["chat"])

# Separate router registered BEFORE the parameterised GET /{session_id} route
# to prevent Starlette from matching "stream" as a session_id and returning 405.
stream_router = APIRouter(prefix="/resume/chat", tags=["chat"])


@stream_router.post("/stream")
async def stream_chat_message(
    request: ResumeChatRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repo)],
    session_repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    agent: Annotated[OllamaResumeChatAgent, Depends(get_chat_agent)],
) -> StreamingResponse:
    session = await session_repo.get(request.session_id, user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    jd: JobDescription | None = None
    if session.jd_json:
        try:
            jd = JobDescription(**session.jd_json)
        except Exception:
            jd = None

    profile: MasterProfile | None = await profile_repo.get_profile(user_id)

    user_msg = ChatMessage(role="user", content=request.message, scope=request.scope)
    await chat_repo.save_message(request.session_id, user_msg)

    async def event_stream():
        import json as _json
        reply_text = ""
        patch: ResumePatch | None = None

        async for event in agent.stream_chat(request=request, jd=jd, profile=profile):
            yield event
            try:
                data = _json.loads(event.removeprefix("data: ").strip())
                if data.get("type") == "done":
                    reply_text = data.get("reply", "")
                elif data.get("type") == "patch":
                    patch = ResumePatch(
                        path=data["path"],
                        updated_value=data["updated_value"],
                        diff_summary=data["diff_summary"],
                    )
            except Exception:
                pass

        assistant_msg = ChatMessage(
            role="assistant",
            content=reply_text,
            scope=request.scope,
            patch=patch,
        )
        await chat_repo.save_message(request.session_id, assistant_msg)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("", response_model=ResumeChatResponse)
async def send_chat_message(
    request: ResumeChatRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repo)],
    session_repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    agent: Annotated[OllamaResumeChatAgent, Depends(get_chat_agent)],
) -> ResumeChatResponse:
    session = await session_repo.get(request.session_id, user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    jd: JobDescription | None = None
    if session.jd_json:
        try:
            jd = JobDescription(**session.jd_json)
        except Exception:
            jd = None

    profile: MasterProfile | None = await profile_repo.get_profile(user_id)

    user_msg = ChatMessage(
        role="user",
        content=request.message,
        scope=request.scope,
    )
    await chat_repo.save_message(request.session_id, user_msg)

    response = await agent.chat(request=request, jd=jd, profile=profile)

    await chat_repo.save_message(request.session_id, response.message)

    return response


@router.get("/{session_id}", response_model=list[ChatMessage])
async def get_chat_history(
    session_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repo)],
    session_repo: Annotated[ResumeSessionRepository, Depends(get_session_repo)],
) -> list[ChatMessage]:
    session = await session_repo.get(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await chat_repo.get_history(session_id)
