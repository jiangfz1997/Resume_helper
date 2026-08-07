# Job Discovery CI/CD

Job Discovery uses one validation workflow and four production deployment
workflows. Deployments are split by runtime ownership so a frontend change does
not rebuild Lambda packages and a crawler change does not redeploy the dashboard
stack.

## Workflow ownership

| Workflow | Owns | AWS write access |
|---|---|---|
| `job-discovery-ci.yml` | Tests, package builds, SAM validation | None |
| `deploy-discovery.yml` | Workday and JobSpy Lambda code | S3 artifacts and Lambda code updates |
| `deploy-dashboard.yml` | Dashboard API, personalized scorer, Cognito, user-data table, and schedules | SAM/CloudFormation deployment |
| `deploy-candidate-profile.yml` | Candidate Profile API, extraction worker, and profile table | SAM/CloudFormation deployment |
| `deploy-frontend.yml` | Vue build in S3 and CloudFront cache | S3 website and CloudFront invalidation |

All four production workflows use the `job-discovery-production` concurrency
group with cancellation disabled. Related deployments can queue, but they cannot
modify production concurrently.

### Job Discovery CI

`.github/workflows/job-discovery-ci.yml` runs for relevant pull requests,
non-`main` branch pushes, and manual dispatches. It:

1. installs development dependencies;
2. runs the Job Discovery test suite;
3. builds all four Job Discovery Lambda packages;
4. validates the dashboard SAM template and zip files; and
5. retains the packages as a GitHub Actions artifact for seven days.

The artifact produced here is stored by GitHub for inspection. It is not copied
to the production S3 bucket, and this workflow never authenticates to AWS.

### Discovery crawler deployment

`.github/workflows/deploy-discovery.yml` runs after crawler-related paths reach
`main`, or by manual dispatch. It tests the service, builds the Workday and
JobSpy packages, uploads immutable objects under
`job-discovery/<git-sha>/`, and updates only:

- `job-discovery-workday`
- `job-discovery-jobspy`

The workflow publishes a Lambda version and waits for each update to report
`Successful`. It does not invoke a crawler, update function configuration,
change DynamoDB tables, or change schedules.

Crawler triggers are intentionally narrower than `job-discovery/src/**`.
Changes to shared domain, repository, source, ingest, and run-report models
redeploy the crawlers. Dashboard-only and scoring-only source changes do not.

### Dashboard API deployment

`.github/workflows/deploy-dashboard.yml` runs after dashboard, scoring, shared
domain/repository, or dashboard infrastructure paths reach `main`, or by manual
dispatch. It builds two packages and deploys `infra/dashboard-api.yaml`:

- `job-dashboard-read`
- `job-discovery-score`

The SAM stack also owns Cognito, the retained dashboard user-data table, the
HTTP API, the personalized-scoring schedule, and the Workday/JobSpy crawler
schedules. The crawler Lambda functions and four shared crawler DynamoDB tables
already existed before this stack and are referenced by name; this stack does
not create or update their code.

### Candidate Profile deployment

`.github/workflows/deploy-candidate-profile.yml` runs after
`candidate-profile/**` changes reach `main`, or by manual dispatch. It deploys
the Candidate Profile API, extraction worker, and retained profile table from
`candidate-profile/infra/candidate-profile.yaml`. It reads the Dashboard stack's
Cognito outputs so both APIs use the same authenticated users.

### Frontend deployment

`.github/workflows/deploy-frontend.yml` runs only for `frontend-vue/**` or its
own workflow file, or by manual dispatch. It reads outputs from the Dashboard
and Candidate Profile stacks, injects them as Vite build settings, syncs the
build to the private website bucket, and invalidates CloudFront.

## GitHub configuration

Create a GitHub environment named `production`. Store configuration as
environment or repository variables unless a value is explicitly identified as
a secret.

### Shared variables

- `AWS_DEPLOY_ROLE_ARN`
- `AWS_REGION`

### Discovery crawler variables

- `LAMBDA_ARTIFACT_BUCKET`
- `WORKDAY_FUNCTION_NAME` (`job-discovery-workday`)
- `JOBSPY_FUNCTION_NAME` (`job-discovery-jobspy`)

### Dashboard API variables

- `LAMBDA_ARTIFACT_BUCKET`
- `DASHBOARD_STACK_NAME`
- `DASHBOARD_ORIGIN`
- `COGNITO_DOMAIN_PREFIX`
- `RECORDS_TABLE_NAME`
- `LISTINGS_TABLE_NAME`
- `GEMINI_MODEL`
- `WORKDAY_FUNCTION_NAME`
- `JOBSPY_FUNCTION_NAME`

### Candidate Profile variables

- `LAMBDA_ARTIFACT_BUCKET`
- `DASHBOARD_STACK_NAME`
- `CANDIDATE_PROFILE_STACK_NAME`
- `CANDIDATE_PROFILE_TABLE_NAME`
- `DASHBOARD_ORIGIN`
- `GEMINI_MODEL`

### Frontend variables

- `DASHBOARD_STACK_NAME`
- `CANDIDATE_PROFILE_STACK_NAME`
- `DASHBOARD_WEB_BUCKET`
- `CLOUDFRONT_DISTRIBUTION_ID`
- `DASHBOARD_ORIGIN`

`GEMINI_API_KEY` is a GitHub Actions environment secret used by the Dashboard
and Candidate Profile deployments. Do not configure it as a variable and never
store it in source. Long-lived AWS access keys are not required because the
workflows assume the deployment role through GitHub OIDC.

Variables named `DASHBOARD_FUNCTION_NAME` and `SCORING_FUNCTION_NAME` are no
longer consumed by these workflows. Those functions are defined by the
Dashboard SAM stack.

## GitHub OIDC and IAM

Restrict the deployment role's OIDC subject to the repository and production
environment:

```text
repo:jiangfz1997/Resume_helper:environment:production
```

The direct crawler deployment needs `s3:PutObject` and `s3:GetObject` for the
artifact prefix, plus `lambda:UpdateFunctionCode`, `lambda:GetFunction`, and
`lambda:GetFunctionConfiguration` for only the two crawler functions.
`lambda:GetFunction` is required by the `function-updated-v2` waiter.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::job-dashboard-artifacts-492832370104-us-east-1-an/job-discovery/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": [
        "arn:aws:lambda:us-east-1:492832370104:function:job-discovery-workday",
        "arn:aws:lambda:us-east-1:492832370104:function:job-discovery-jobspy"
      ]
    }
  ]
}
```

The SAM workflows also need their existing scoped CloudFormation, Lambda, API
Gateway, Cognito, IAM, S3, EventBridge Scheduler, and DynamoDB permissions. The
frontend workflow needs website-bucket writes and CloudFront invalidation. The
same OIDC role can be reused initially; separate deployment roles can be added
later if stricter isolation becomes useful.

## Artifact retention and rollback

Enable S3 versioning and add a lifecycle rule for the `job-discovery/` prefix,
for example deleting packages after 90 days. To roll back crawler code, update a
function from the immutable package key belonging to a previous commit. For
SAM-managed services, redeploy the desired repository revision so code and
infrastructure remain consistent.

## Current infrastructure boundary

The workflow split does not migrate existing AWS resources between
CloudFormation stacks:

- Workday and JobSpy Lambda functions remain pre-existing resources updated
  directly by `deploy-discovery.yml`.
- The four shared crawler DynamoDB tables remain external resources referenced
  by name.
- Crawler and scoring schedules remain managed by the Dashboard SAM stack.

Moving these existing resources into a dedicated Discovery stack requires a
staged CloudFormation retain/import migration. It should not be combined with a
routine workflow refactor because declaring an existing physical resource in a
new stack can fail with `AlreadyExists` or cause an unintended replacement.

The first migration guard is already present in `dashboard-api.yaml`: the
discovery Scheduler role and both crawler schedules use `DeletionPolicy` and
`UpdateReplacePolicy` set to `Retain`. The stack also outputs the generated
Scheduler role name needed for a later manual import. These attributes do not
move or disable resources; they only prevent CloudFormation from deleting them
when the resources are detached from the Dashboard stack in a later phase.
