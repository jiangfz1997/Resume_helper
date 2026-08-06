# Job discovery CI/CD

Job discovery uses separate workflows for validation, Lambda code deployment,
and dashboard infrastructure deployment.

## Workflows

### Job discovery CI

`.github/workflows/job-discovery-ci.yml` runs for pull requests, non-main
branch pushes, and manual dispatches when `job-discovery` changes. It:

1. installs the development dependencies;
2. runs the unit tests;
3. builds the Workday, JobSpy, dashboard, and personalized-scoring Lambda packages;
4. validates the zip files; and
5. retains them as a GitHub Actions artifact for seven days.

This workflow never connects to AWS.

### Lambda deployment

`.github/workflows/deploy-job-discovery-lambdas.yml` runs after a
runtime-affecting change is pushed to `main`, or when manually dispatched. It
repeats the tests and builds, authenticates to AWS through GitHub OIDC, uploads
immutable packages under `job-discovery/<git-sha>/`, and updates these existing
functions:

- `job-discovery-workday`
- `job-discovery-jobspy`
- `job-dashboard-read`
- `job-discovery-score`

The probe Lambda is intentionally excluded. A shared source change rebuilds all
four production functions because every package contains a copy of
`src/job_discovery`.

The workflow publishes a Lambda version and waits for each update to report
`Successful`. It does not invoke the crawlers, change their EventBridge
schedules, or update function configuration.

### Dashboard deployment

`.github/workflows/deploy-dashboard.yml` remains manually triggered. It manages
the SAM stack and the Vue application. Its dashboard Lambda package now uses an
immutable S3 key passed to CloudFormation, preventing a later SAM deployment
from restoring an older fixed-key package.

## GitHub configuration

Create a GitHub environment named `production`. Add these environment or
repository variables for Lambda deployment:

- `AWS_DEPLOY_ROLE_ARN`
- `AWS_REGION` (`us-east-1` for the current deployment)
- `LAMBDA_ARTIFACT_BUCKET`
- `WORKDAY_FUNCTION_NAME` (`job-discovery-workday`)
- `JOBSPY_FUNCTION_NAME` (`job-discovery-jobspy`)
- `DASHBOARD_FUNCTION_NAME` (`job-dashboard-read`)
- `SCORING_FUNCTION_NAME` (`job-discovery-score`)

The existing dashboard workflow additionally requires:

- `DASHBOARD_STACK_NAME`
- `DASHBOARD_WEB_BUCKET`
- `CLOUDFRONT_DISTRIBUTION_ID`
- `DASHBOARD_ORIGIN`
- `COGNITO_DOMAIN_PREFIX`
- `RECORDS_TABLE_NAME`
- `LISTINGS_TABLE_NAME`
- `GEMINI_MODEL`

The dashboard workflow also requires the GitHub Actions secret
`GEMINI_API_KEY`.

Do not store long-lived AWS access keys in GitHub. Configure the deployment
role to trust GitHub's OIDC provider and restrict its subject to:

```text
repo:jiangfz1997/Resume_helper:environment:production
```

The role needs `s3:PutObject` for the artifact prefix and
`s3:GetObject` for uploaded packages, plus `lambda:UpdateFunctionCode`,
`lambda:GetFunction`, and `lambda:GetFunctionConfiguration` for the four
functions. `lambda:GetFunction` is required by the `function-updated-v2` waiter. A minimal policy for
the code-deployment workflow is:

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
        "arn:aws:lambda:us-east-1:492832370104:function:job-discovery-jobspy",
        "arn:aws:lambda:us-east-1:492832370104:function:job-dashboard-read",
        "arn:aws:lambda:us-east-1:492832370104:function:job-discovery-score"
      ]
    }
  ]
}
```

The role trust policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::492832370104:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:jiangfz1997/Resume_helper:environment:production"
        }
      }
    }
  ]
}
```

The dashboard SAM workflow needs its existing CloudFormation, API Gateway,
Cognito, IAM, S3, and CloudFront deployment permissions as well. It also needs
`dynamodb:CreateTable`, `dynamodb:DescribeTable`, `dynamodb:UpdateTable`,
`dynamodb:DeleteTable`, `dynamodb:TagResource`, `dynamodb:UntagResource`, and
`dynamodb:ListTagsOfResource` for the retained dashboard user-data table. The
same role can be reused initially; splitting infrastructure and code-deployment
roles can be done later. The SAM deploy role also needs EventBridge Scheduler
lifecycle permissions and scoped IAM role/`iam:PassRole` permissions for the
scheduled scoring target.

## Artifact retention and rollback

Enable S3 versioning and add a lifecycle rule for the `job-discovery/` prefix,
for example deleting packages after 90 days. To roll back, manually dispatch a
workflow revision containing the desired code, or call
`lambda update-function-code` with the package key from a previous commit.

Production deploys are serialized by the `job-discovery-production`
concurrency group. Feature branches cannot update AWS.
