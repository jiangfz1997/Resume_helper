"""Pydantic contracts for the Phase 0 reachability probe."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class ProbeTier(str, Enum):
    """Which class of source a target belongs to."""

    ATS = "ats"
    AGGREGATOR = "aggregator"


class ProbeOutcome(str, Enum):
    """Normalized verdict for a single probe attempt.

    EMPTY is deliberately distinct from OK: a 200 response carrying zero
    postings is the primary silent-failure mode for aggregator sources.
    NOT_FOUND is distinct from BLOCKED so a stale target token is never
    misread as an IP-level block.
    """

    OK = "ok"
    EMPTY = "empty"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"
    SKIPPED = "skipped"


class WorkdayTarget(BaseModel):
    kind: Literal["workday"] = "workday"
    key: str
    name: str
    tenant: str
    site_id: str
    base_url: str
    search_text: str = "Software Engineer"

    @property
    def tier(self) -> ProbeTier:
        return ProbeTier.ATS


class GreenhouseTarget(BaseModel):
    kind: Literal["greenhouse"] = "greenhouse"
    key: str
    name: str
    board_token: str

    @property
    def tier(self) -> ProbeTier:
        return ProbeTier.ATS


class LeverTarget(BaseModel):
    kind: Literal["lever"] = "lever"
    key: str
    name: str
    company: str

    @property
    def tier(self) -> ProbeTier:
        return ProbeTier.ATS


class AggregatorTarget(BaseModel):
    kind: Literal["aggregator"] = "aggregator"
    key: str
    name: str
    site: str
    search_term: str
    location: str
    country_indeed: str = "canada"
    results_wanted: int = 10
    hours_old: int = 168

    @property
    def tier(self) -> ProbeTier:
        return ProbeTier.AGGREGATOR


ProbeTarget = Annotated[
    Union[WorkdayTarget, GreenhouseTarget, LeverTarget, AggregatorTarget],
    Field(discriminator="kind"),
]


class TargetSet(BaseModel):
    """Root of targets.yaml."""

    workday: list[WorkdayTarget] = Field(default_factory=list)
    greenhouse: list[GreenhouseTarget] = Field(default_factory=list)
    lever: list[LeverTarget] = Field(default_factory=list)
    aggregator: list[AggregatorTarget] = Field(default_factory=list)

    def all_targets(self) -> list[ProbeTarget]:
        return [*self.workday, *self.greenhouse, *self.lever, *self.aggregator]

    def by_tier(self, tier: ProbeTier) -> list[ProbeTarget]:
        return [t for t in self.all_targets() if t.tier is tier]


class ProbeResult(BaseModel):
    key: str
    name: str
    kind: str
    tier: ProbeTier
    outcome: ProbeOutcome
    http_status: int | None = None
    item_count: int = 0
    elapsed_ms: int = 0
    sample_title: str | None = None
    detail: str | None = None


class EgressInfo(BaseModel):
    """Where the probe actually exited to the internet from."""

    ip: str | None = None
    org: str | None = None
    region: str | None = None

    @property
    def looks_like_aws(self) -> bool:
        haystack = f"{self.org or ''}".lower()
        return "amazon" in haystack or "aws" in haystack or "16509" in haystack


class ProbeReport(BaseModel):
    environment: str
    egress: EgressInfo
    started_at: datetime
    python_version: str
    jobspy_version: str | None = None
    results: list[ProbeResult] = Field(default_factory=list)

    def outcome_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            counts[result.outcome.value] = counts.get(result.outcome.value, 0) + 1
        return counts
