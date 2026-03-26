import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.base import IUserRepository
from app.models.data_models import UserCreate, UserUpdate
from app.models.db_models import UserORM


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: UserCreate, hashed_password: str) -> UserORM:
        user = UserORM(
            email=data.email,
            hashed_password=hashed_password,
            full_name=data.full_name,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> UserORM | None:
        result = await self._session.execute(select(UserORM).where(UserORM.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserORM | None:
        result = await self._session.execute(select(UserORM).where(UserORM.email == email))
        return result.scalar_one_or_none()

    async def update(self, user_id: uuid.UUID, data: UserUpdate) -> UserORM | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(user, field, value)
        await self._session.commit()
        await self._session.refresh(user)
        return user
