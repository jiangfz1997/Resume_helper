from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from job_discovery.domain.filters import DEFAULT_INCLUDE_TITLE_KEYWORDS
from job_discovery.domain.models import ScoringProfile

DEFAULT_MAX_REQUIRED_YEARS = 5


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
    # Upper bound on the years a posting may demand. Unrelated to
    # years.MAX_PLAUSIBLE_YEARS, which is an extraction noise guard -- setting
    # this low is a search preference, setting that low would break extraction.
    max_required_years: int | None = Field(default=DEFAULT_MAX_REQUIRED_YEARS, ge=0, le=20)


class DiscoverySettings(DiscoverySettingsInput):
    config_version: int = 1
    updated_at: datetime | None = None


class ScoringProfileInput(BaseModel):
    skills: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    location_preference: str | None = None
    prefers_new_grad: bool = False
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
            prefers_new_grad=self.prefers_new_grad,
        )
