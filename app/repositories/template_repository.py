import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.base import IGlobalTemplateRepository, IUserTemplateRepository
from app.models.data_models import TemplateCreate, TemplateRead
from app.models.db_models import GlobalTemplateORM, UserTemplateORM


class GlobalTemplateRepository(IGlobalTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: TemplateCreate) -> TemplateRead:
        row = GlobalTemplateORM(
            name=data.name,
            industry=data.industry,
            style_tag=data.style_tag,
            description=data.description,
            preamble=data.preamble,
            body_example=data.body_example,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_global_read(row)

    async def list_all(self) -> list[TemplateRead]:
        result = await self._session.execute(
            select(GlobalTemplateORM).order_by(GlobalTemplateORM.created_at.desc())
        )
        return [_to_global_read(r) for r in result.scalars().all()]

    async def get_by_id(self, template_id: uuid.UUID) -> TemplateRead | None:
        result = await self._session.execute(
            select(GlobalTemplateORM).where(GlobalTemplateORM.id == template_id)
        )
        row = result.scalar_one_or_none()
        return _to_global_read(row) if row else None

    async def delete(self, template_id: uuid.UUID) -> bool:
        row = await self._session.get(GlobalTemplateORM, template_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True


class UserTemplateRepository(IUserTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID, data: TemplateCreate) -> TemplateRead:
        row = UserTemplateORM(
            user_id=user_id,
            name=data.name,
            industry=data.industry,
            style_tag=data.style_tag,
            description=data.description,
            preamble=data.preamble,
            body_example=data.body_example,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_user_read(row)

    async def list_by_user(self, user_id: uuid.UUID) -> list[TemplateRead]:
        result = await self._session.execute(
            select(UserTemplateORM)
            .where(UserTemplateORM.user_id == user_id)
            .order_by(UserTemplateORM.created_at.desc())
        )
        return [_to_user_read(r) for r in result.scalars().all()]

    async def get_by_id(self, template_id: uuid.UUID) -> TemplateRead | None:
        result = await self._session.execute(
            select(UserTemplateORM).where(UserTemplateORM.id == template_id)
        )
        row = result.scalar_one_or_none()
        return _to_user_read(row) if row else None

    async def delete(self, template_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        row = await self._session.get(UserTemplateORM, template_id)
        if row is None or row.user_id != user_id:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True


def _to_global_read(row: GlobalTemplateORM) -> TemplateRead:
    return TemplateRead(
        id=row.id,
        name=row.name,
        industry=row.industry,
        style_tag=row.style_tag,
        description=row.description,
        preamble=row.preamble,
        body_example=row.body_example,
        created_at=row.created_at,
        source="global",
    )


def _to_user_read(row: UserTemplateORM) -> TemplateRead:
    return TemplateRead(
        id=row.id,
        name=row.name,
        industry=row.industry,
        style_tag=row.style_tag,
        description=row.description,
        preamble=row.preamble,
        body_example=row.body_example,
        created_at=row.created_at,
        source="user",
    )
