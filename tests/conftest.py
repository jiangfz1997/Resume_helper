import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_auth_service, get_current_user_id, get_profile_repo, get_user_repo
from app.models.data_models import MasterProfile, TokenResponse, UserRead
from main import app

TEST_USER_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def make_user_orm_mock(
    user_id: uuid.UUID = TEST_USER_ID,
    email: str = "test@example.com",
    full_name: str = "Test User",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.full_name = full_name
    user.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return user


def make_master_profile(user_id: uuid.UUID = TEST_USER_ID) -> MasterProfile:
    return MasterProfile(user_id=user_id, full_name="Test User")


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_auth_service() -> MagicMock:
    svc = MagicMock()
    svc.register = AsyncMock()
    svc.login = AsyncMock()
    svc.decode_token = MagicMock()
    return svc


@pytest_asyncio.fixture
async def client(
    mock_user_repo: AsyncMock,
    mock_profile_repo: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_user_repo] = lambda: mock_user_repo
    app.dependency_overrides[get_profile_repo] = lambda: mock_profile_repo
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(
    mock_auth_service: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
