# Dashboard deployment

The dashboard is deployed by `.github/workflows/deploy-dashboard.yml`. The
workflow tests and packages the read API, deploys its SAM stack, builds the Vue
application from the stack outputs, syncs the build to S3, and invalidates
CloudFront.

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

The IAM role trust policy must restrict GitHub's OIDC subject to this repository
and the `production` environment. The role needs only the CloudFormation,
Lambda, API Gateway, Cognito, IAM, S3, and CloudFront permissions used by this
stack and deployment workflow.

Run the workflow manually from the GitHub Actions page. Configure a required
reviewer on the `production` environment if an approval gate is desired. After
the deployment has been verified, a later change can enable deployment on
merges to `main`.

Lambda-only code changes are deployed separately by
`.github/workflows/deploy-job-discovery-lambdas.yml`. See
`docs/job-discovery-cicd.md` for triggers, permissions, and rollback details.
