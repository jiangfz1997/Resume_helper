import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user_id, get_user_repo
from app.models.data_models import UserRead, UserUpdate
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> UserRead:
    logger.debug("get_me | user_id=%s", user_id)
    user = await repo.get_by_id(user_id)
    if user is None:
        logger.warning("get_me | not found | user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.debug("get_me | success | email=%s", user.email)
    return UserRead.model_validate(user)


@router.put("/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> UserRead:
    logger.debug("update_me | user_id=%s fields=%s", user_id, data.model_dump(exclude_none=True))
    user = await repo.update(user_id, data)
    if user is None:
        logger.warning("update_me | not found | user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("update_me | success | user_id=%s", user_id)
    return UserRead.model_validate(user)
