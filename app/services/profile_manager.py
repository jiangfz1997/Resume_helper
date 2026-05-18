import uuid

from app.models.data_models import MasterProfile, ParsedProfileDraft, ProfileUpdate, Skill
from app.repositories.profile_repository import ProfileRepository


class ProfileManager:
    def __init__(self, profile_repo: ProfileRepository) -> None:
        self._repo = profile_repo

    async def load_master_profile(self, user_id: uuid.UUID) -> MasterProfile | None:
        return await self._repo.get_profile(user_id)

    async def save_profile(self, user_id: uuid.UUID, data: ProfileUpdate) -> None:
        await self._repo.upsert_profile(user_id, data)

    async def append_parsed_draft(
        self, user_id: uuid.UUID, draft: ParsedProfileDraft
    ) -> MasterProfile | None:
        await self._repo.append_profile_data(user_id, draft)
        if draft.skills:
            await self._repo.append_skills(user_id, draft.skills)
        return await self._repo.get_profile(user_id)

    async def replace_parsed_draft(
        self, user_id: uuid.UUID, draft: ParsedProfileDraft
    ) -> MasterProfile | None:
        update = ProfileUpdate(
            work_experiences=draft.work_experiences or None,
            educations=draft.educations or None,
            projects=draft.projects or None,
            summary=draft.summary or None,
        )
        await self._repo.upsert_profile(user_id, update)
        if draft.skills:
            await self._repo.append_skills(user_id, draft.skills)
        return await self._repo.get_profile(user_id)

    async def append_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None:
        await self._repo.append_skills(user_id, skills)

    async def replace_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None:
        await self._repo.replace_skills(user_id, skills)
