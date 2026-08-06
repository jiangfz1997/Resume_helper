# Handoff: job-discovery data + pipeline, for dashboard design and old-service cloud deploy

Written 2026-08-05 for handing to another agent. Scope: this file only describes
**what already exists and is deployed** (job-discovery crawler + DynamoDB). It
does not include the separate LangGraph resume backend/frontend — see the
"Old service" section at the bottom for what's known about that from this
project's side.

> Update, 2026-08-06: the scoring/profile and dashboard sections below describe
> the original single-profile implementation and are retained as historical
> probe evidence. The current branch uses one shared crawler configuration,
> Cognito-user-specific profiles and assessments, and a separate scheduled
> `job-discovery-score` Lambda. The authoritative current design is
> `../../docs/job-discovery-multi-user.md`.

**Status as of 2026-08-05, end of day**: both Lambdas manually verified
end-to-end against real AWS (search -> normalize -> dedup -> filter ->
ingest -> Gemini score), repository now has 73 `JobRecord`s accumulated
across both sources, weak-key dedup flagging confirmed firing correctly on
real duplicate requisitions, scoring confirmed using the real `ScoringProfile`
(not an empty one) with qualitatively sensible results. Only remaining
unverified piece: an actual **unattended** EventBridge-triggered run has not
yet been observed in CloudWatch Logs — every run so far was a manual
console Test. Check `/aws/lambda/job-discovery-workday` and
`/aws/lambda/job-discovery-jobspy` log groups after the next scheduled UTC
trigger (12:00 / 17:00 / 23:00) for an invocation with no matching manual
Test action, to close this out.

## 1. Pipeline architecture

Two independent AWS Lambda functions write into the **same four DynamoDB
tables**. Both run the same domain pipeline, just against different sources:

```
JobSource.search(query)          -> list[SourceJobRef]        (lightweight handles)
JobSource.fetch_detail(ref)      -> SourceJobObservation       (source-native, raw)
normalize.build_candidate(obs)   -> NormalizedJobCandidate     (canonical fields)
deduplicate.compute_dedup_keys() -> list[DedupKey]
filters.apply_hard_filters()     -> EligibilityDecision
JobRepository.upsert_observation() -> JobRecord + JobSourceListing   (persisted)
[optional] score.score_eligible_jobs() -> Gemini coarse_score written onto JobRecord
```

| Lambda | Sources | Package |
|---|---|---|
| `job-discovery-workday` | Workday CXS API: TD, CIBC, RBC (see `EMPLOYERS` in `lambda_workday/lambda_function.py`) | ~3.5MB, stdlib `urllib` only |
| `job-discovery-jobspy` | Indeed + LinkedIn via `python-jobspy` | ~35MB, numpy/pandas/tls-client |

Both are invoked manually today (Test button in Lambda console). EventBridge
scheduling (3x/day) is planned but **not yet wired up**.

Coarse scoring (Gemini) is optional per-run: gated on `GEMINI_API_KEY` +
`GEMINI_MODEL` env vars both being set. `ScoringProfile` (skills, target
titles, min years experience, location preference) is currently passed in
the Lambda **event payload**, not persisted anywhere — this is the piece
still being finalized (see open items below).

## 2. Dedup model — why a job can have multiple "listings"

The same posting often appears on more than one source (e.g. TD posts to its
own Workday board **and** it gets indexed by Indeed). To avoid duplicate
cards in a dashboard, the schema separates two entities:

- **`JobRecord`** — one canonical entity per real-world job posting.
- **`JobSourceListing`** — one row per `(job_id, source)` pairing. A single
  `JobRecord` can have 1..N listings.

Dedup key priority, strongest first (`DedupKeyKind`):
1. `source_id` — exact same `(source, source_job_id)` seen again -> update, no new listing.
2. `apply_url` — same final application URL across sources -> **auto-merge** (new listing on existing job).
3. `description_hash` — identical JD text -> **auto-merge**.
4. `company_title_location` — same company+title+location but different apply URL/JD -> **does NOT auto-merge**. Sets `possible_duplicate_of` + `duplicate_matched_by` on a *new* `JobRecord` instead, for human/UI review. (This tier exists because two genuinely different TD requisitions with identical title+company+location were seen in production — auto-merging would have silently destroyed one posting's data.)

**Dashboard implication**: when listing jobs, dedupe by `job_id`, not by
`(source, source_job_id)`. If you want to show "seen on Indeed + Workday",
join `JobSourceListing` rows by `job_id`. If you want to flag possible
duplicates for a human to confirm, surface any `JobRecord` where
`possible_duplicate_of is not None`.

## 3. DynamoDB schema — 4 tables, all PAY_PER_REQUEST, zero GSIs

All reads are primary-key reads with `ConsistentRead=True`. There is
deliberately no GSI (a GSI-based design caused a real eventual-consistency
bug in production and was removed — see `dynamodb_schema.py` docstring).
Practical effect for a dashboard: **listing/filtering all jobs is a full
table Scan**, fine at current volume (tens–hundreds of records), but note
it if the dashboard ever wants server-side pagination beyond what
`repository.query()` already does client-side.

### Table: `job-discovery-records` (PK: `job_id`)

This is the table a dashboard reads from for the main job list/cards.

| Field | Type | Notes |
|---|---|---|
| `job_id` | string (UUID) | partition key |
| `canonical_title` | string | |
| `canonical_company` | string | |
| `canonical_location` | string \| absent | |
| `workplace_type` | string enum | `onsite` \| `hybrid` \| `remote` \| `unknown` |
| `description` | string \| absent | full JD text |
| `description_chars` | int | |
| `description_hash` | string \| absent | |
| `salary_text` | string \| absent | raw salary text, not parsed |
| `required_years_min` / `required_years_max` | int \| absent | extracted by Gemini from the JD text during coarse scoring (2026-08-05+); absent if scoring hasn't run yet or Gemini didn't find an explicit years requirement |
| `requirement_keywords` | list[string] | concrete requirement keywords (skills/tools/certs/degrees) extracted by Gemini from the JD text during coarse scoring; `[]` if scoring hasn't run yet |
| `possible_duplicate_of` | string (UUID) \| absent | set only on a weak-key match, see section 2 |
| `duplicate_matched_by` | string enum \| absent | which `DedupKeyKind` triggered the flag |
| `eligibility_status` | string enum | `eligible` \| `excluded` \| `review` — **primary filter for a dashboard** |
| `filter_codes` | list[string enum] | why excluded/review: `location_mismatch`, `excluded_title`, `review_title`, `title_not_relevant`, `description_too_short`, `description_missing` |
| `filter_version` | string \| absent | |
| `coarse_score` | int \| absent | Gemini score, 1-10 presumably (not hard-clamped in schema); absent if scoring hasn't run |
| `coarse_score_reasoning` | string \| absent | free text from Gemini |
| `score_model` | string \| absent | e.g. `gemini-3.6-flash` |
| `score_version` | string \| absent | currently always `"v1"` |
| `scored_at` | ISO datetime string \| absent | |
| `user_status` | string | legacy shared field; the dashboard does not use it because user-specific state now lives in its own Cognito-keyed table |
| `first_discovered_run_id` | string \| absent | stable hourly discovery batch that first created the canonical job; older rows fall back to an hour bucket derived from `created_at` in the dashboard API |
| `created_at` / `updated_at` | ISO datetime string | |

### Table: `job-discovery-listings` (PK: `job_id`, SK: `source_job_id_key`)

`source_job_id_key` = `f"{source}#{source_job_id}"`, e.g. `"workday#R_1500774"`.
Querying by `job_id` alone returns every listing (every source) for that job
in one call — this is how a dashboard would render "seen on: Workday, Indeed".

| Field | Type | Notes |
|---|---|---|
| `job_id` | string (UUID) | partition key, FK to records table |
| `source_job_id_key` | string | sort key, `source#source_job_id` |
| `listing_id` | string (UUID) | |
| `source` | string enum | `workday` \| `greenhouse` \| `lever` \| `indeed` \| `linkedin` |
| `source_job_id` | string | source-native ID |
| `source_url` | string | |
| `apply_url_canonical` | string \| absent | normalized application URL — **the link a dashboard "Apply" button should use** |
| `posted_at` | ISO datetime \| absent | |
| `posted_at_raw` | string \| absent | e.g. `"Posted Today"` |
| `posted_at_quality` | string enum | `exact` \| `relative` \| `inferred` \| `unknown` — LinkedIn is `unknown` for essentially every listing, fall back to `first_seen_at` for sorting |
| `first_seen_at` / `last_seen_at` | ISO datetime | |
| `first_miss_at` | ISO datetime \| absent | set when a listing stops appearing in search results (staleness tracking, not yet acted upon) |
| `consecutive_misses` | int | |
| `last_seen_run_id` | string | |
| `status` | string enum | `active` \| `stale` \| `closed` — nothing currently transitions this out of `active` |

### Table: Dashboard user state (managed by the dashboard SAM stack)

The authenticated dashboard owns a separate PAY_PER_REQUEST table with
`user_id` as the partition key and `entity_key` as the sort key. `JOB#<uuid>`
items store viewed/status state and `RUN#<run_id>` items store whether a user
opened a discovery batch. This state is not written into the shared JobRecord,
so the two supported Cognito users remain isolated.

### Table: `job-discovery-dedup-keys` (PK: `key`)

Internal to the repository's dedup cascade (`key` = `f"{kind}#{value}"` ->
`job_id`). Not useful for a dashboard directly.

### Table: `job-discovery-source-lookup` (PK: `source_job_id_key`)

Internal index (`source#source_job_id` -> `job_id`), exists purely so the
repository can answer "have we already seen this exact listing" with a
consistent primary-key read instead of a GSI. Not useful for a dashboard
directly.

## 4. What a first dashboard read path probably looks like

```
1. Scan job-discovery-records, filter eligibility_status == "eligible"
   (or expose all three tabs: eligible / review / excluded)
2. Sort by coarse_score desc (nulls last) as default, or by updated_at desc
3. For each job_id shown, Query job-discovery-listings by job_id to get
   apply_url_canonical + source badges
4. Show possible_duplicate_of as a "possible duplicate of <other job>" badge
   when present, do not hide the job
```

`repository.query(JobQuery(...))` in `domain/interfaces.py` already
implements steps 1-2 server-side if the dashboard backend calls into this
Python package directly rather than re-implementing DynamoDB access; `filter
by source` and `min_score` are also supported by `JobQuery`.

## 5. EventBridge schedule (configured 2026-08-05)

One rule, `job-discovery-schedule`, cron `cron(0 12,17,23 * * ? *)` (UTC) =
08:00/13:00/19:00 America/Toronto during EDT. Two targets, one per Lambda,
each with a **Constant (JSON text)** input — this is the fixed
`ScoringProfile` + search params baked in, since a scheduled run has no
human to fill in a Test event. This profile is duplicated in both targets'
JSON, not read from any shared store (see open item below: not persisted
anywhere else).

Target: `job-discovery-workday`
```json
{
  "search_term": "Software Engineer",
  "max_results": 10,
  "accepted_locations": [],
  "skills": ["Python", "Java", "AWS"],
  "target_titles": ["Software Engineer", "QA Engineer"],
  "location_preference": "Ontario, Canada preferred (Canada-wide acceptable)"
}
```

Target: `job-discovery-jobspy`
```json
{
  "search_term": "Software Engineer",
  "location": "Canada",
  "hours_old": 24,
  "max_results": 15,
  "accepted_locations": [],
  "sites": ["indeed", "linkedin"],
  "skills": ["Python", "Java", "AWS"],
  "target_titles": ["Software Engineer", "QA Engineer"],
  "location_preference": "Ontario, Canada preferred (Canada-wide acceptable)"
}
```

Note `accepted_locations: []` — see `filters.py`'s convention, empty list
means no hard location filter at all (Canada-wide). `location_preference`
is soft, only used by Gemini scoring, not by `apply_hard_filters()`.

Caveat: this cron is UTC and does not shift with US/Canada DST. When EDT
ends (~November), the actual local trigger times will drift by an hour
until the cron is manually updated.

## 6. Lambda deployment details (for the "old service to cloud" half of this handoff)

- Both Lambdas: Python 3.13 runtime, x86_64.
- Env vars required together (all four or none — partial config raises at
  startup): `RECORDS_TABLE`, `LISTINGS_TABLE`, `DEDUP_KEYS_TABLE`,
  `SOURCE_LOOKUP_TABLE`. Currently pointed at `job-discovery-records` /
  `job-discovery-listings` / `job-discovery-dedup-keys` /
  `job-discovery-source-lookup`.
- Optional: `GEMINI_API_KEY`, `GEMINI_MODEL` (currently `gemini-3.6-flash`,
  confirmed working end-to-end on both Lambdas as of 2026-08-05 — a live
  `job-discovery-workday` run returned 26 scored records, `coarse_score`
  1-10, `scoring_skipped_reason: null`. Free-tier model names have gone
  stale within days before, so re-verify if scoring starts failing later).
  Note `score_eligible_jobs()` scores **every** `eligible` `JobRecord` in
  the repository each run, not just the current invocation's — the workday
  run's scores included Indeed/LinkedIn-sourced companies (Stripe, eBay,
  Scotiabank) written by the other Lambda, confirming both Lambdas share
  state correctly through the four tables.
- IAM: each Lambda's execution role needs `dynamodb:GetItem`, `PutItem`,
  `UpdateItem`, `Query`, `Scan` on all four tables (inline policy, per-role).
- No API Gateway in front of either Lambda today. Invocation is
  console-Test-button (manual) plus the EventBridge schedule above (3x/day).
  If the dashboard needs on-demand "run now" triggering, that's unbuilt.
- Event payload shape both Lambdas accept (all fields optional):
  `{"search_term": str, "location": str, "hours_old": int, "max_results": int,
  "accepted_locations": [str], "sites": [str] (jobspy only),
  "include_title_keywords": [str], "skills": [str], "target_titles": [str],
  "min_years_experience": int, "location_preference": str}`.

## 7. Open items relevant to dashboard/deploy design (not yet resolved)

- **ScoringProfile is not persisted in a shared store.** It's duplicated as
  literal JSON in two EventBridge targets (section 5) — editing it means
  editing both rule targets by hand in the console, and it drifts if only
  one gets updated. If the dashboard wants to let the user edit their
  profile, that's a new write path (e.g. move the profile to S3/DynamoDB and
  have both Lambdas read it, replacing the EventBridge constant-JSON
  approach) with no existing backend support yet.
- `user_status` on `JobRecord` is a free string, not an enum, and nothing
  writes to it besides the `"new"` default — this is presumably the field
  a dashboard's "mark as applied" action should update, but there's no
  existing API for it (would be a direct DynamoDB `update_item` today).
- `required_years_min`/`required_years_max`/`requirement_keywords` are now
  populated by `GeminiCoarseScorer` (2026-08-05+, merged into the existing
  coarse-scoring call, no extra Gemini request) but only for jobs that have
  actually been scored — jobs excluded by hard filters, or scored before
  this change shipped, will still show these fields as absent/`[]`.
- Persisted `status` on `JobSourceListing` (`active`/`stale`/`closed`) does not
  transition automatically. The dashboard now derives a reversible lifecycle
  from `last_seen_at` (7 days stale, 30 days archived) without deleting data
  after N consecutive misses even though `consecutive_misses` is tracked.
- No API layer exists between DynamoDB and a dashboard today — a dashboard
  backend would either read DynamoDB directly (same IAM pattern as the
  Lambdas) or a new read API needs to be built.

## 7. Old service (LangGraph resume backend + frontend)

Lives in the parent repo, outside `job-discovery/`. Not detailed here since
this document is scoped to job-discovery's own data/pipeline — the other
agent should inspect that part of the repo directly for its current
architecture, deployment state (currently local-only), and whether it's
FastAPI+Mangum-Lambda-shaped or needs a container (Fargate/ECS) — the
relevant constraint if it turns out to need multi-turn LangGraph checkpointer
state or streaming responses, neither of which fit a bare Lambda well.
