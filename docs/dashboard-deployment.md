# Dashboard deployment

The dashboard backend is deployed by `.github/workflows/deploy-dashboard.yml`.
The workflow tests and packages the authenticated dashboard API and personalized
scorer, then deploys their SAM stack. It does not build or publish Vue.

The static Vue application is deployed independently by
`.github/workflows/deploy-frontend.yml`. That workflow reads both backend stack
outputs, builds the frontend, syncs it to S3, and invalidates CloudFront.

Create a GitHub `production` environment, configure GitHub Actions OIDC for this
repository, and add these repository or environment variables:

- `AWS_DEPLOY_ROLE_ARN`
- `AWS_REGION`
- `LAMBDA_ARTIFACT_BUCKET`
- `DASHBOARD_STACK_NAME`
- `DASHBOARD_WEB_BUCKET`
- `CLOUDFRONT_DISTRIBUTION_ID`
- `DASHBOARD_ORIGIN`
- `COGNITO_DOMAIN_PREFIX`
- `RECORDS_TABLE_NAME`
- `LISTINGS_TABLE_NAME`
- `GEMINI_MODEL`
- `WORKDAY_FUNCTION_NAME`
- `JOBSPY_FUNCTION_NAME`

The frontend workflow additionally requires:

- `CANDIDATE_PROFILE_STACK_NAME`
- `DASHBOARD_WEB_BUCKET`
- `CLOUDFRONT_DISTRIBUTION_ID`

Add `GEMINI_API_KEY` as a GitHub Actions **secret**, not a variable.

The IAM role trust policy must restrict GitHub's OIDC subject to this repository
and the `production` environment. The role needs the CloudFormation, Lambda,
API Gateway, Cognito, IAM, S3, CloudFront, EventBridge Scheduler, and DynamoDB permissions used by this
stack and deployment workflow. DynamoDB is required because the stack creates
the retained user-data table and the scheduled personalized-scoring worker.

Each workflow runs only after its relevant paths reach `main`, and each can be
dispatched manually from GitHub Actions. Pull requests only run validation and
never update AWS. Configure a required reviewer on the `production`
environment if an approval gate is desired.

The first deployment after this change creates the
`job-discovery-user-data` DynamoDB table, the `job-discovery-score` Lambda, and
authenticated profile/settings routes. CloudFormation retains the table if the
stack is deleted or replaced. No new GitHub variable is required because the
Lambdas receive the generated table name through `USER_DATA_TABLE`.

The stack also owns the Workday and JobSpy EventBridge Scheduler resources. It
uses the existing `WORKDAY_FUNCTION_NAME` and `JOBSPY_FUNCTION_NAME` repository
variables, so no additional GitHub configuration is required. Disable the old
console-created crawler schedules before the first deployment to prevent
duplicate invocations.

See `docs/job-discovery-multi-user.md` for the shared-crawl/personal-score model
and the one-time crawler IAM/environment change.

Crawler-only code changes are deployed separately by
`.github/workflows/deploy-discovery.yml`. Dashboard and scoring changes remain
owned by `.github/workflows/deploy-dashboard.yml`. See
`docs/job-discovery-cicd.md` for triggers, permissions, and rollback details.
