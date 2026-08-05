# Phase 1: domain contracts

`job_discovery/domain/` and `job_discovery/repositories/memory.py`. No AWS
here — this proves the pipeline (search → fetch → normalize → dedup → filter
→ persist) is correct against an in-memory repository before Phase 2 wires it
into Lambda handlers.

## Data flow, four distinct types

```
JobSource.search()        -> SourceJobRef
JobSource.fetch_detail()  -> SourceJobObservation   (source-native, unnormalized)
normalize.build_candidate() -> NormalizedJobCandidate (canonical, not yet matched)
JobRepository.upsert_observation() -> JobRecord + JobSourceListing (persisted)
```

Never conflate these. `SourceJobObservation` carries whatever a source
handed back; `NormalizedJobCandidate` carries computed canonical values;
`JobRecord`/`JobSourceListing` are what the repository actually stores. A
`JobRecord` can have several `JobSourceListing`s — this is what lets the same
posting be seen through both Indeed and Workday without either overwriting
the other, which is not a hypothetical: the Lambda probe run on 2026-08-05
showed TD's `Software Engineer III` reachable through both, with an identical
`job_url_direct`/apply URL.

## Deferred out of Phase 1, on purpose

- **`SourceTask` / `DiscoveryRun`** (architecture doc 7.2) — run-tracking
  models belong to the dispatcher, which does not exist yet.
  `domain.models.SearchQuery` is the minimal stand-in `JobSource.search()`
  needs; it is not that model and should not grow into it.
- **`reconcile_source_run` / miss counting** — `JobSourceListing` already has
  `first_miss_at`, `consecutive_misses`, and `status`, because the LinkedIn
  probe showed 70% listing churn between two runs minutes apart: one miss
  must never mean "closed." But deciding *when* a miss counts requires
  knowing a source run completed successfully and covered this listing's
  query/location — that needs `SourceTask`, so the reconciliation logic
  waits for it rather than half-implementing it now.
- **`SqliteJobRepository`** — no concrete need yet; the in-memory
  implementation plus its contract tests are what validate the design. Add
  SQLite when local runs need to persist across process restarts.
- **Required-years filtering** — needs text extraction from the description
  that has not been built. `filters.py` does not fake a threshold in its
  absence.
- **async** — every current I/O path (jobspy, urllib-based ATS clients) is
  synchronous; introducing asyncio now has no driver behind it.

## Running tests

```bash
python -m pytest
```

`pyproject.toml` sets `pythonpath = ["src"]`, so no editable install is
needed. 23 tests, covering:

- URL normalization is idempotent and keeps non-tracking query params
  (`normalize.py`'s docstring explains why blanket query-string stripping
  is wrong for ATS URLs).
- `posted_at` parsing: ISO exact, relative ("2 days ago"), and the LinkedIn
  case (`None` → `UNKNOWN`, not treated as "just posted").
- The cross-source TD case above, reproduced against `InMemoryJobRepository`.
- The weak `company_title_location` key does not merge different companies.
- `first_seen_at` survives a repeat observation; `last_seen_at` advances;
  `description_chars` is recomputed, never trusted from the source.
- Filter policy: short/missing description → `review`, not excluded, not a
  browser-fallback trigger (that fallback was deliberately dropped —
  ApplyPilot's Playwright-based JD rescue does not belong in a Lambda-first
  design); `staff/principal/director` → excluded; `senior/lead` → review.
