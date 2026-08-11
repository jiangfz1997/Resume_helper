"""Lambda runner for Simplify's Canada and GitHub new-grad feeds."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from job_discovery.application.ingest import ingest_observation
from job_discovery.dashboard.models import DiscoveryRunReport
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, SearchQuery, SourceName
from job_discovery.domain.settings import DiscoverySettings
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository
from job_discovery.repositories.factory import build_repository
from job_discovery.sources.simplify_source import SimplifyCanadaSource, SimplifyGitHubSource

log = logging.getLogger()
log.setLevel(logging.INFO)

SOURCE_FACTORIES = {
    "canada": (SourceName.SIMPLIFY_CANADA, SimplifyCanadaSource, 500),
    "github": (SourceName.SIMPLIFY_GITHUB, SimplifyGitHubSource, 500),
}


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    del context
    event = event or {}
    settings = _load_settings(event)
    started_at = datetime.now(timezone.utc)
    run_id = str(event.get("run_id") or f"lambda-{started_at.strftime('%Y-%m-%dT%H:00Z')}")
    repository, repository_backend = build_repository()
    filter_config = FilterConfig(
        filter_version=f"config-{settings.config_version}",
        accepted_locations=settings.accepted_locations,
        include_title_keywords=settings.include_title_keywords,
        exclude_title_keywords=settings.exclude_title_keywords,
        review_title_keywords=settings.review_title_keywords,
        min_description_chars=settings.min_description_chars,
        max_required_years=settings.max_required_years,
    )

    feeds = event.get("feeds", ["canada", "github"])
    listings: list[dict[str, Any]] = []
    for feed in feeds:
        source_config = SOURCE_FACTORIES.get(str(feed))
        if source_config is None:
            listings.append({"feed": feed, "stage": "search", "error": f"unknown feed {feed!r}"})
            continue
        source_name, factory, default_limit = source_config
        source = factory()
        limit = int(event.get(f"{feed}_max_results", default_limit))
        query = SearchQuery(source=source_name, query="new grad", max_results=limit, run_id=run_id)
        try:
            refs = source.search(query)
        except Exception as exc:
            log.warning("Simplify %s search failed: %s", feed, exc)
            listings.append({"feed": feed, "stage": "search", "error": str(exc)[:200]})
            continue

        for ref in refs:
            if not _matches_saved_scope(source.summary(ref), settings):
                continue
            try:
                observation = source.fetch_detail(ref)
                result = ingest_observation(observation, repository, filter_config)
                record = repository.get_record(result.job_id)
                listing = repository.get_listing(observation.source, observation.source_job_id)
                assert record is not None and listing is not None
                listings.append({
                    "feed": feed,
                    "source_job_id": observation.source_job_id,
                    "job_id": str(result.job_id),
                    "upsert_status": result.status.value,
                    "matched_by": result.matched_by.value if result.matched_by else None,
                    "title": record.canonical_title,
                    "company": record.canonical_company,
                    "location": record.canonical_location,
                    "eligibility_status": record.eligibility_status.value,
                    "is_new_grad": record.is_new_grad,
                    "apply_url_canonical": listing.apply_url_canonical,
                })
            except Exception as exc:
                log.warning("Simplify %s detail failed for %s: %s", feed, ref.source_job_id, exc)
                listings.append({
                    "feed": feed, "source_job_id": ref.source_job_id,
                    "stage": "detail", "error": str(exc)[:200],
                })

    counts = {"eligible": 0, "excluded": 0, "review": 0}
    for item in listings:
        status = item.get("eligibility_status")
        if status in counts:
            counts[status] += 1
    completed_at = datetime.now(timezone.utc)
    report = DiscoveryRunReport(
        run_id=run_id,
        runner="simplify",
        started_at=started_at,
        completed_at=completed_at,
        sources=[SOURCE_FACTORIES[feed][0].value for feed in feeds if feed in SOURCE_FACTORIES],
        observed_count=sum(1 for item in listings if item.get("job_id")),
        new_jobs_count=sum(1 for item in listings if item.get("upsert_status") == "job_created"),
        eligible_count=counts["eligible"],
        review_count=counts["review"],
        excluded_count=counts["excluded"],
        error_count=sum(1 for item in listings if item.get("error")),
    )
    report_persisted = _record_run_report(report)
    all_records = repository.query(JobQuery(limit=1000))
    return {
        "run_id": run_id,
        "repository_backend": repository_backend,
        "feeds_scanned": feeds,
        "this_run_eligible": counts["eligible"],
        "this_run_review": counts["review"],
        "this_run_excluded": counts["excluded"],
        "total_jobs_in_repository": len(all_records),
        "listings": listings,
        "run_report_persisted": report_persisted,
    }


def _matches_saved_scope(row: dict[str, Any], settings: DiscoverySettings) -> bool:
    """Avoid hundreds of detail requests for tracks/locations the saved
    discovery configuration would deterministically exclude anyway."""
    title = str(row.get("title") or "").casefold()
    if settings.include_title_keywords and not any(
        keyword.casefold() in title for keyword in settings.include_title_keywords
    ):
        return False
    raw_locations = row.get("locations") or row.get("location") or ""
    if isinstance(raw_locations, list):
        location = " ".join(
            str(value.get("value") if isinstance(value, dict) else value) for value in raw_locations
        ).casefold()
    else:
        location = str(raw_locations).casefold()
    if settings.accepted_locations and not any(
        accepted.casefold() in location for accepted in settings.accepted_locations
    ):
        return False
    return True


def _load_settings(event: dict[str, Any]) -> DiscoverySettings:
    table_name = os.environ.get("USER_DATA_TABLE")
    if table_name:
        return DynamoDBDashboardUserStateRepository(table_name).get_discovery_settings()
    return DiscoverySettings(
        accepted_locations=event.get("accepted_locations", ["Canada", "Toronto", "Vancouver", "Montreal"]),
        include_title_keywords=event.get(
            "include_title_keywords", FilterConfig(filter_version="v1").include_title_keywords
        ),
    )


def _record_run_report(report: DiscoveryRunReport) -> bool:
    table_name = os.environ.get("USER_DATA_TABLE")
    if not table_name:
        return False
    try:
        DynamoDBDashboardUserStateRepository(table_name).record_discovery_run(report)
        return True
    except Exception:
        log.exception("failed to persist Simplify discovery run report")
        return False


if __name__ == "__main__":
    import sys
    cli_event = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(lambda_handler(cli_event, None), indent=2, ensure_ascii=False))
