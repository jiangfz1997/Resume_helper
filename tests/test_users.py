import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_USER_ID, make_user_orm_mock


class TestGetMe:
    async def test_success(
        self, client: AsyncClient, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.get_by_id.return_value = make_user_orm_mock()
        response = await client.get("/users/me")
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "test@example.com"
        assert body["full_name"] == "Test User"
        assert body["id"] == str(TEST_USER_ID)
        mock_user_repo.get_by_id.assert_awaited_once_with(TEST_USER_ID)

    async def test_user_not_found_returns_404(
        self, client: AsyncClient, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.get_by_id.return_value = None
        response = await client.get("/users/me")
        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    async def test_no_token_returns_401(self) -> None:
        from httpx import ASGITransport, AsyncClient
        from main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/users/me")
        assert response.status_code == 401


class TestUpdateMe:
    async def test_success(
        self, client: AsyncClient, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.update.return_value = make_user_orm_mock(full_name="Updated Name")
        response = await client.put("/users/me", json={"full_name": "Updated Name"})
        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated Name"
        mock_user_repo.update.assert_awaited_once()

    async def test_update_email(
        self, client: AsyncClient, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.update.return_value = make_user_orm_mock(email="updated@example.com")
        response = await client.put("/users/me", json={"email": "updated@example.com"})
        assert response.status_code == 200
        assert response.json()["email"] == "updated@example.com"

    async def test_user_not_found_returns_404(
        self, client: AsyncClient, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.update.return_value = None
        response = await client.put("/users/me", json={"full_name": "Name"})
        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"
