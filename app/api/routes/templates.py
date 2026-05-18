import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_admin_id,
    get_current_user_id,
    get_global_template_repo,
    get_user_template_repo,
)
from app.models.data_models import TemplateCreate, TemplateRead
from app.repositories.template_repository import GlobalTemplateRepository, UserTemplateRepository

# DEPRECATED: LaTeX template workflow is no longer active.
# All endpoints are kept for backwards compatibility but are not called by the frontend.
router = APIRouter(prefix="/templates", tags=["templates (deprecated)"])


@router.get("", response_model=list[TemplateRead])
async def list_templates(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    global_repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
    user_repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> list[TemplateRead]:
    global_templates = await global_repo.list_all()
    user_templates = await user_repo.list_by_user(user_id)
    return global_templates + user_templates


@router.post("/global", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_global_template(
    body: TemplateCreate,
    _admin_id: Annotated[uuid.UUID, Depends(get_current_admin_id)],
    repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
) -> TemplateRead:
    return await repo.create(body)


@router.get("/global", response_model=list[TemplateRead])
async def list_global_templates(
    _user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
) -> list[TemplateRead]:
    return await repo.list_all()


@router.delete("/global/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_global_template(
    template_id: uuid.UUID,
    _admin_id: Annotated[uuid.UUID, Depends(get_current_admin_id)],
    repo: Annotated[GlobalTemplateRepository, Depends(get_global_template_repo)],
) -> None:
    deleted = await repo.delete(template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")


@router.post("/mine", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_user_template(
    body: TemplateCreate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> TemplateRead:
    return await repo.create(user_id, body)


@router.get("/mine", response_model=list[TemplateRead])
async def list_user_templates(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> list[TemplateRead]:
    return await repo.list_by_user(user_id)


@router.delete("/mine/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_template(
    template_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    repo: Annotated[UserTemplateRepository, Depends(get_user_template_repo)],
) -> None:
    deleted = await repo.delete(template_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
