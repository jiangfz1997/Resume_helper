# Job Discovery CI/CD

Job Discovery uses one validation workflow and five production deployment
workflows. Deployments are split by runtime ownership so a frontend change does
not rebuild Lambda packages and a crawler change does not redeploy the dashboard
stack.

## Workflow ownership

| Workflow | Owns | AWS write access |
|---|---|---|
| `job-discovery-ci.yml` | Tests, package builds, SAM validation | None |
| `deploy-discovery.yml` | Workday and JobSpy Lambda code | S3 artifacts and Lambda code updates |
| `deploy-discovery-infra.yml` | Crawler schedules and Scheduler invocation role | CloudFormation deployment |
| `deploy-dashboard.yml` | Dashboard API, personalized scorer, Cognito, user-data table, and scoring schedule | SAM/CloudFormation deployment |
| `deploy-candidate-profile.yml` | Candidate Profile API, extraction worker, and profile table | SAM/CloudFormation deployment |
| `deploy-frontend.yml` | Vue build in S3 and CloudFront cache | S3 website and CloudFront invalidation |

All five production workflows use the `job-discovery-production` concurrency
group with cancellation disabled. Related deployments can queue, but they cannot
modify production concurrently.

### Job Discovery CI

`.github/workflows/job-discovery-ci.yml` runs for relevant pull requests,
non-`main` branch pushes, and manual dispatches. It:

1. installs development dependencies;
2. runs the Job Discovery test suite;
3. builds all four Job Discovery Lambda packages;
4. validates the Dashboard and Discovery infrastructure templates and zip files; and
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

### Discovery infrastructure deployment

`.github/workflows/deploy-discovery-infra.yml` runs only when
`infra/discovery.yaml` or the workflow itself reaches `main`, or by manual
dispatch. It updates the already imported `job-discovery` CloudFormation stack
and never packages or updates crawler Lambda code. The stable stack name lives
in the workflow; the imported role and function names are read from the stack's
existing parameters, so no additional GitHub variables are required.

### Dashboard API deployment

`.github/workflows/deploy-dashboard.yml` runs after dashboard, scoring, shared
domain/repository/source, or dashboard infrastructure paths reach `main`, or by
manual dispatch. It builds three packages and deploys `infra/dashboard-api.yaml`:

- `job-dashboard-read`
- `job-discovery-score`
- `job-discovery-simplify`

The SAM stack also owns Cognito, the retained dashboard user-data table, the
HTTP API, the personalized-scoring schedule, and both the function and daily
schedule for the new Simplify crawler. The legacy Workday/JobSpy functions and
schedules plus the four shared crawler DynamoDB tables remain outside this stack.

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

The infrastructure workflows also need their existing scoped CloudFormation, Lambda, API
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

- Workday and JobSpy Lambda functions remain pre-existing resources updated
  directly by `deploy-discovery.yml`.
- The four shared crawler DynamoDB tables remain external resources referenced
  by name.
- The scoring schedule remains managed by the Dashboard SAM stack.
- The crawler schedules and Scheduler invocation role are managed by the
  dedicated `job-discovery` CloudFormation stack.

### Discovery stack migration record

The existing resources moved through a staged retain/import migration. Before
detachment, the Dashboard stack applied `DeletionPolicy` and
`UpdateReplacePolicy` set to `Retain` to the discovery Scheduler role and both
crawler schedules. Removing them from `dashboard-api.yaml` therefore releases
CloudFormation ownership without deleting or disabling the physical resources.

`infra/discovery.yaml` is the template for the dedicated Discovery stack. Its
first deployment was a CloudFormation resource import rather than a normal
create operation. The retained resources were imported with these identifiers:

| Logical ID | Identifier | Existing value |
|---|---|---|
| `DiscoverySchedulerRole` | `RoleName` | Role name from either managed schedule's Target execution-role ARN |
| `WorkdayDiscoverySchedule` | `Name` | `job-discovery-workday-managed` |
| `JobSpyDiscoverySchedule` | `Name` | `job-discovery-jobspy-managed` |

The stack is named `job-discovery` and reached `IMPORT_COMPLETE` with drift
status `IN_SYNC`. The template intentionally has no `Outputs` section because
CloudFormation import change sets cannot add or modify stack outputs. Outputs
can be added later in a normal stack update if another service needs them.

The GitHub OIDC deployment policy must allow the existing CloudFormation
change-set actions for both `stack/job-dashboard/*` and
`stack/job-discovery/*`. The existing `role/job-dashboard-*` IAM scope and
`schedule/default/*` Scheduler scope already cover the imported resources.
For the current account, add the following stack ARN beside the existing
Dashboard stack ARN in `ManageDashboardCloudFormationStack`; keep the existing
change-set ARN and action list unchanged:

```text
arn:aws:cloudformation:us-east-1:492832370104:stack/job-discovery/*
```
