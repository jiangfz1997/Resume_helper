from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from app.core.config import settings
from app.models.data_models import TokenResponse, UserCreate, UserRead
from app.models.db_models import UserORM
from app.repositories.user_repository import UserRepository

_pwd_context = PasswordHash((BcryptHasher(),))


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self._repo = user_repo

    def _hash_password(self, password: str) -> str:
        return _pwd_context.hash(password)

    def _verify_password(self, plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)

    def _create_token(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        return jwt.encode(
            {"sub": user_id, "exp": expire},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

    def decode_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            return payload.get("sub")
        except JWTError:
            return None

    async def register(self, data: UserCreate) -> UserRead:
        hashed = self._hash_password(data.password)
        user: UserORM = await self._repo.create(data, hashed)
        return UserRead.model_validate(user)

    async def login(self, email: str, password: str) -> Optional[TokenResponse]:
        user = await self._repo.get_by_email(email)
        if user is None or not self._verify_password(password, user.hashed_password):
            return None
        return TokenResponse(access_token=self._create_token(str(user.id)))
