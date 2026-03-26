import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_auth_service
from app.models.data_models import TokenResponse, UserCreate, UserRead
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserRead:
    logger.debug("register | email=%s", data.email)
    try:
        result = await auth_service.register(data)
        logger.info("register | success | user_id=%s email=%s", result.id, result.email)
        return result
    except IntegrityError:
        logger.warning("register | conflict | email=%s already exists", data.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    print("login | email=%s", form_data.username)
    logger.debug("login | email=%s", form_data.username)
    result = await auth_service.login(form_data.username, form_data.password)
    if result is None:
        logger.warning("login | failed | email=%s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    logger.info("login | success | email=%s", form_data.username)
    return result
