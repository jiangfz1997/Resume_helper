from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from job_discovery.domain.filters import DEFAULT_INCLUDE_TITLE_KEYWORDS
from job_discovery.domain.models import ScoringProfile


class DiscoverySettingsInput(BaseModel):
    search_terms: list[str] = Field(
        default_factory=lambda: ["Software Engineer", "SDET", "QA Engineer"], min_length=1
    )
    jobspy_location: str = "Canada"
    hours_old: int = Field(default=24, ge=1, le=168)
    jobspy_max_results: int = Field(default=15, ge=1, le=100)
    workday_max_results: int = Field(default=10, ge=1, le=100)
    sites: list[str] = Field(default_factory=lambda: ["indeed", "linkedin"], min_length=1)
    accepted_locations: list[str] = Field(default_factory=list)
    include_title_keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE_TITLE_KEYWORDS))
    exclude_title_keywords: list[str] = Field(
        default_factory=lambda: ["staff", "principal", "director", "vp", "vice president", "head of"]
    )
    review_title_keywords: list[str] = Field(default_factory=lambda: ["senior", "sr.", "lead"])
    min_description_chars: int = Field(default=300, ge=0, le=10000)


class DiscoverySettings(DiscoverySettingsInput):
    config_version: int = 1
    updated_at: datetime | None = None


class ScoringProfileInput(BaseModel):
    skills: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    location_preference: str | None = None
    active: bool = True


class UserScoringProfile(ScoringProfileInput):
    user_id: str
    profile_version: int = 1
    updated_at: datetime

    def to_scoring_profile(self) -> ScoringProfile:
        return ScoringProfile(
            skills=self.skills,
            target_titles=self.target_titles,
            min_years_experience=self.min_years_experience,
            location_preference=self.location_preference,
        )
