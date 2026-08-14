from __future__ import annotations

from typing import Protocol

from candidate_profile.domain.models import (
    ApplicationListQuery,
    ApplicationStatus,
    CandidateProfile,
    CandidateProfileInput,
    CreateApplicationFromJob,
    ExtractedJobInfo,
    FetchedPage,
    JobApplication,
    UpdateApplicationFields,
)


class CandidateProfileRepository(Protocol):
    def get_profile(self, user_id: str) -> CandidateProfile | None: ...

    def save_profile(self, user_id: str, data: CandidateProfileInput) -> CandidateProfile: ...

    def create_application_from_job(self, user_id: str, data: CreateApplicationFromJob) -> JobApplication: ...

    def create_application_pending(self, user_id: str, url: str) -> JobApplication: ...

    def complete_application_extraction(
        self, user_id: str, application_id: str, extracted: ExtractedJobInfo, raw_html: str | None
    ) -> None: ...

    def fail_application_extraction(self, user_id: str, application_id: str, error: str) -> None: ...

    def list_applications(self, user_id: str, query: ApplicationListQuery | None = None) -> list[JobApplication]: ...

    def get_application(self, user_id: str, application_id: str) -> JobApplication | None: ...

    def update_application_status(
        self, user_id: str, application_id: str, status: ApplicationStatus, note: str | None
    ) -> JobApplication | None: ...

    def update_application_fields(
        self, user_id: str, application_id: str, data: UpdateApplicationFields
    ) -> JobApplication | None: ...

    def delete_application(self, user_id: str, application_id: str) -> None: ...


class PageFetcher(Protocol):
    def load(self, url: str) -> FetchedPage:
        """Read ``url`` into text plus an optional markup snapshot.

        Not "return the HTML": Workday postings are read from a JSON API
        that has no page HTML to hand back, so the reader owns the
        conversion and callers never detag anything themselves. Raises
        PageFetchError on failure.
        """
        ...


class JobInfoExtractor(Protocol):
    def extract(self, page_text: str) -> ExtractedJobInfo:
        """Pull company/title/location out of already-detagged page text.

        Never rewrites ``jd_text`` itself -- that is taken verbatim from the
        page so the saved record stays a faithful copy of the posting.
        """
        ...
