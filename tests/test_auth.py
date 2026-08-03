import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from app.models.data_models import TokenResponse, UserRead
from tests.conftest import TEST_USER_ID


class TestRegister:
    async def test_success(
        self, auth_client: AsyncClient, mock_auth_service: MagicMock
    ) -> None:
        mock_auth_service.register.return_value = UserRead(
            id=TEST_USER_ID,
            email="new@example.com",
            full_name="New User",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        response = await auth_client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "secret123", "full_name": "New User"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["full_name"] == "New User"
        assert "id" in body

    async def test_duplicate_email_returns_409(
        self, auth_client: AsyncClient, mock_auth_service: MagicMock
    ) -> None:
        mock_auth_service.register.side_effect = IntegrityError(
            "INSERT INTO users ...", {}, Exception("duplicate key value violates unique constraint")
        )
        response = await auth_client.post(
            "/auth/register",
            json={"email": "existing@example.com", "password": "secret123", "full_name": "User"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "Email already registered"

    async def test_short_password_returns_422(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            "/auth/register",
            json={"email": "a@example.com", "password": "short", "full_name": "User"},
        )
        assert response.status_code == 422

    async def test_invalid_email_returns_422(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "secret123", "full_name": "User"},
        )
        assert response.status_code == 422


class TestLogin:
    async def test_success(
        self, auth_client: AsyncClient, mock_auth_service: MagicMock
    ) -> None:
        mock_auth_service.login.return_value = TokenResponse(access_token="fake.jwt.token")
        response = await auth_client.post(
            "/auth/login",
            data={"username": "test@example.com", "password": "secret123"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "fake.jwt.token"
        assert body["token_type"] == "bearer"

    async def test_invalid_credentials_returns_401(
        self, auth_client: AsyncClient, mock_auth_service: MagicMock
    ) -> None:
        mock_auth_service.login.return_value = None
        response = await auth_client.post(
            "/auth/login",
            data={"username": "test@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"
