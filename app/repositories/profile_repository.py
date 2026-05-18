import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.base import IProfileRepository
from app.models.data_models import (
    ContactInfo,
    Education,
    MasterProfile,
    ParsedProfileDraft,
    ProfileUpdate,
    Project,
    Skill,
    WorkExperience,
)
from app.models.db_models import UserORM, UserProfileORM, UserSkillORM


class ProfileRepository(IProfileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_profile(self, user_id: uuid.UUID) -> MasterProfile | None:
        user = (
            await self._session.execute(select(UserORM).where(UserORM.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            return None

        profile = (
            await self._session.execute(
                select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
        ).scalar_one_or_none()

        skill_rows = (
            await self._session.execute(
                select(UserSkillORM).where(UserSkillORM.user_id == user_id)
            )
        ).scalars().all()

        contact_info: ContactInfo | None = None
        if profile and profile.contact_info:
            contact_info = ContactInfo.model_validate(profile.contact_info)

        return MasterProfile(
            user_id=user_id,
            full_name=user.full_name,
            summary=profile.summary if profile else None,
            contact_info=contact_info,
            work_experiences=[
                WorkExperience(**e) for e in (profile.work_experiences if profile else [])
            ],
            educations=[
                Education(**e) for e in (profile.educations if profile else [])
            ],
            projects=[
                Project(**e) for e in (profile.projects if profile else [])
            ],
            skills=[
                Skill(category=s.category, name=s.name, proficiency=s.proficiency)
                for s in skill_rows
            ],
        )

    async def upsert_profile(self, user_id: uuid.UUID, data: ProfileUpdate) -> None:
        profile = (
            await self._session.execute(
                select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
        ).scalar_one_or_none()

        updates = data.model_dump(exclude_none=True)

        if profile is None:
            self._session.add(UserProfileORM(user_id=user_id, **updates))
        else:
            for field, value in updates.items():
                setattr(profile, field, value)
            profile.updated_at = datetime.now(timezone.utc)

        await self._session.commit()

    async def append_profile_data(self, user_id: uuid.UUID, data: ParsedProfileDraft) -> None:
        profile = (
            await self._session.execute(
                select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
        ).scalar_one_or_none()

        draft = data.model_dump()

        if profile is None:
            self._session.add(
                UserProfileORM(
                    user_id=user_id,
                    work_experiences=draft["work_experiences"],
                    educations=draft["educations"],
                    projects=draft["projects"],
                    summary=data.summary,
                )
            )
        else:
            if data.work_experiences:
                existing_exp_keys = {
                    (e.get("company", "").lower(), e.get("title", "").lower())
                    for e in (profile.work_experiences or [])
                }
                new_exps = [
                    e for e in draft["work_experiences"]
                    if (e.get("company", "").lower(), e.get("title", "").lower())
                    not in existing_exp_keys
                ]
                if new_exps:
                    profile.work_experiences = (profile.work_experiences or []) + new_exps

            if data.educations:
                existing_edu_keys = {
                    (e.get("institution", "").lower(), e.get("degree", "").lower())
                    for e in (profile.educations or [])
                }
                new_edus = [
                    e for e in draft["educations"]
                    if (e.get("institution", "").lower(), e.get("degree", "").lower())
                    not in existing_edu_keys
                ]
                if new_edus:
                    profile.educations = (profile.educations or []) + new_edus

            if data.projects:
                existing_proj_keys = {
                    e.get("name", "").lower()
                    for e in (profile.projects or [])
                }
                new_projs = [
                    e for e in draft["projects"]
                    if e.get("name", "").lower() not in existing_proj_keys
                ]
                if new_projs:
                    profile.projects = (profile.projects or []) + new_projs

            if data.summary:
                profile.summary = data.summary
            profile.updated_at = datetime.now(timezone.utc)

        await self._session.commit()

    async def append_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None:
        existing = await self.get_skills(user_id)
        existing_names = {s.name.lower() for s in existing}
        for skill in skills:
            if skill.name.lower() not in existing_names:
                existing_names.add(skill.name.lower())
                self._session.add(
                    UserSkillORM(
                        user_id=user_id,
                        category=skill.category,
                        name=skill.name,
                        proficiency=skill.proficiency.value if skill.proficiency else "",
                    )
                )
        await self._session.commit()

    async def replace_skills(self, user_id: uuid.UUID, skills: list[Skill]) -> None:
        await self._session.execute(
            delete(UserSkillORM).where(UserSkillORM.user_id == user_id)
        )
        for skill in skills:
            self._session.add(
                UserSkillORM(
                    user_id=user_id,
                    category=skill.category,
                    name=skill.name,
                    proficiency=skill.proficiency.value if skill.proficiency else "",
                )
            )
        await self._session.commit()

    async def get_skills(self, user_id: uuid.UUID) -> list[Skill]:
        rows = (
            await self._session.execute(
                select(UserSkillORM).where(UserSkillORM.user_id == user_id)
            )
        ).scalars().all()
        return [Skill(category=r.category, name=r.name, proficiency=r.proficiency) for r in rows]
