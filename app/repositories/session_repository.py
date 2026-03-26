import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_models import (
    JobDescription,
    MasterProfile,
    MatchingReport,
    PipelineConfig,
    TailoredResumeDraft,
)
from app.models.db_models import ResumeSessionORM


class ResumeSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID, jd_text: str) -> ResumeSessionORM:
        row = ResumeSessionORM(user_id=user_id, jd_text=jd_text, status="analyzing")
        self._session.add(row)
        await self._session.commit()
        return row

    async def update_after_analysis(
        self,
        session_id: uuid.UUID,
        profile: MasterProfile,
        jd: JobDescription,
        matching_report: MatchingReport,
        match_score: float,
    ) -> None:
        row = await self._get_row(session_id)
        if row is None:
            return
        row.profile_snapshot_json = profile.model_dump(mode="json")
        row.jd_json = jd.model_dump(mode="json")
        row.matching_report_json = matching_report.model_dump(mode="json")
        row.match_score = match_score
        row.job_title = jd.title
        row.company = jd.company
        row.status = "analyzed"
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def mark_generating(
        self,
        session_id: uuid.UUID,
        selected_experience_indices: list[int] | None,
        selected_project_indices: list[int] | None,
        template_id: uuid.UUID | None,
        template_source: str | None,
        config: PipelineConfig,
    ) -> None:
        row = await self._get_row(session_id)
        if row is None:
            return
        row.selected_experience_indices = selected_experience_indices
        row.selected_project_indices = selected_project_indices
        row.template_id = template_id
        row.template_source = template_source
        row.pipeline_config_json = config.model_dump(mode="json")
        row.status = "generating"
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def update_draft(
        self, session_id: uuid.UUID, draft: TailoredResumeDraft
    ) -> None:
        row = await self._get_row(session_id)
        if row is None:
            return
        row.tailored_draft_json = draft.model_dump(mode="json")
        row.status = "draft_ready"
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def mark_failed(self, session_id: uuid.UUID, error: str) -> None:
        row = await self._get_row(session_id)
        if row is None:
            return
        row.status = "failed"
        row.error_message = error
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def get(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ResumeSessionORM | None:
        result = await self._session.execute(
            select(ResumeSessionORM).where(
                ResumeSessionORM.id == session_id,
                ResumeSessionORM.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[ResumeSessionORM]:
        result = await self._session.execute(
            select(ResumeSessionORM)
            .where(ResumeSessionORM.user_id == user_id)
            .order_by(ResumeSessionORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def delete(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        row = await self.get(session_id, user_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    async def _get_row(self, session_id: uuid.UUID) -> ResumeSessionORM | None:
        result = await self._session.execute(
            select(ResumeSessionORM).where(ResumeSessionORM.id == session_id)
        )
        return result.scalar_one_or_none()
