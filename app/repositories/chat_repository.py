import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_models import ChatMessage, ChatScope, ResumePatch
from app.models.db_models import SessionChatMessageORM


class ChatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_message(
        self,
        session_id: uuid.UUID,
        message: ChatMessage,
    ) -> SessionChatMessageORM:
        row = SessionChatMessageORM(
            id=message.id or uuid.uuid4(),
            session_id=session_id,
            role=message.role,
            content=message.content,
            scope_path=message.scope.path if message.scope else None,
            scope_label=message.scope.label if message.scope else None,
            patch=message.patch.model_dump() if message.patch else None,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def get_history(self, session_id: uuid.UUID) -> list[ChatMessage]:
        result = await self._db.execute(
            select(SessionChatMessageORM)
            .where(SessionChatMessageORM.session_id == session_id)
            .order_by(SessionChatMessageORM.created_at.asc())
        )
        rows = result.scalars().all()
        return [_orm_to_message(row) for row in rows]


def _orm_to_message(row: SessionChatMessageORM) -> ChatMessage:
    scope: Optional[ChatScope] = None
    if row.scope_path and row.scope_label:
        scope = ChatScope(path=row.scope_path, label=row.scope_label)

    patch: Optional[ResumePatch] = None
    if row.patch:
        patch = ResumePatch(**row.patch)

    return ChatMessage(
        id=row.id,
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        scope=scope,
        patch=patch,
        created_at=row.created_at,
    )
