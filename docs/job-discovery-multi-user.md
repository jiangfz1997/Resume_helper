# Two-user job discovery architecture

## Ownership boundaries

The production design separates shared market data from personal decisions:

```text
EventBridge Scheduler (10:00, 14:00, and 20:00 America/Toronto)
  -> Workday Lambda + JobSpy Lambda
  -> one shared normalized/deduplicated job collection
  -> job-discovery-records + job-discovery-listings

45 minutes after each crawl
  -> job-discovery-score
  -> reads every active Cognito user's scoring profile
  -> writes a separate assessment for each (user_id, job_id)

Dashboard
  -> shared job facts and discovery runs
  -> signed-in user's score, viewed state, and workflow status
```

There is no duplicate crawl per user. Search terms and hard-filter settings are
shared; skills, target roles, experience, location preference, scores, viewed
state, and saved/applied/rejected status are personal.

## User data table

The dashboard SAM stack creates the retained on-demand table
`job-discovery-user-data` with partition key `user_id` and sort key
`entity_key`:

| Partition / sort key | Purpose |
|---|---|
| Cognito `sub` / `PROFILE#SCORING` | Personal lightweight scoring profile |
| Cognito `sub` / `JOB#<job_id>` | Personal score plus viewed/workflow state |
| Cognito `sub` / `RUN#<run_id>` | Whether that user opened the crawl batch |
| `SYSTEM` / `SETTINGS#DISCOVERY` | One shared crawler/filter configuration |

Saving a profile increments `profile_version`. A score is reusable only when
its user, job description hash, prompt version, and profile version match. A
profile edit therefore causes that user to be rescored without affecting the
other user.

The shared `JobRecord` stores only JD-derived facts such as required years and
requirement keywords. A personal fit score is never written into the shared
record by the new scoring worker. Legacy shared score fields remain readable
for migration compatibility but the dashboard does not display them.

## API and UI

All routes use the existing Cognito JWT authorizer. The Cognito `sub` claim is
the user ID; the browser never supplies an arbitrary user ID.

- `GET/PUT /profile/scoring`: current user's profile.
- `GET/PUT /settings/discovery`: shared discovery settings.
- `GET /user-state`: current user's scores, views, run views, and statuses.
- `GET /scoring/queue`: current user's scored and pending counts.
- `POST /jobs/{job_id}/score`: queues one job for the authenticated user.
- Existing `/jobs` and `/runs` routes return shared discovery data.

The Vue `Job Settings` page makes the ownership boundary explicit. Both users
may currently edit shared discovery settings, which is acceptable for the
two-person deployment. Add an admin Cognito group check before expanding to
untrusted users.

## Scheduling and capacity

Workday and JobSpy run at 10:00, 14:00, and 20:00 in `America/Toronto`;
personalized scoring follows at 10:45, 14:45, and 20:45. EventBridge Scheduler
applies daylight-saving changes automatically. The Dashboard stack owns only
the scoring schedule. The retained crawler schedules and invocation role are
temporarily unmanaged while they wait for import into the Discovery stack.
Each scoring invocation loads at most 20 eligible jobs and evaluates them for
every active profile.
This conservative batch size leaves retry headroom inside Lambda's 15-minute
maximum. Repeated runs skip unchanged `(user, job, profile, prompt)` versions.

The crawler schedules target the existing `job-discovery-workday` and
`job-discovery-jobspy` functions. The dedicated Discovery stack will manage the
invocation role and schedules without replacing or recreating those Lambdas.

## Required runtime configuration

The dashboard deployment needs GitHub secret `GEMINI_API_KEY` and variable
`GEMINI_MODEL`. It creates `job-discovery-score` and its schedule.

For the crawler Lambdas to read dashboard-managed shared settings, set:

```text
USER_DATA_TABLE=job-discovery-user-data
```

Their execution roles also need `dynamodb:GetItem` and `dynamodb:PutItem` on
that table. `GetItem` loads shared settings; `PutItem` writes one compact
source-health report per run. Until this is
configured, crawler event payload/default settings remain the compatibility
fallback. Gemini environment variables are no longer needed on crawler
functions.

The dashboard derives lifecycle from the newest listing `last_seen_at`: less
than 7 days is active, 7-29 days is stale, and 30 days or more is archived.
This is a reversible display state; no DynamoDB job is deleted.

The crawler deployment workflow requires `WORKDAY_FUNCTION_NAME` and
`JOBSPY_FUNCTION_NAME`. The scoring function remains SAM-managed and does not
use a direct-deployment function-name variable.

The retained schedules use the names `job-discovery-workday-managed` and
`job-discovery-jobspy-managed`. Do not create another set while the retained
resources wait for import, or each crawler will be invoked twice.
