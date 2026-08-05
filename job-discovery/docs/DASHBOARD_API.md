# Dashboard read API

This stack exposes the existing job records and listings through an authenticated, read-only HTTP API. It does not create or modify the crawler tables.

## Build

```powershell
cd job-discovery\lambda_dashboard
python build.py
```

## Deploy

Install AWS SAM CLI, then run from `job-discovery`:

```powershell
sam validate --template-file infra\dashboard-api.yaml
sam deploy --guided --template-file infra\dashboard-api.yaml
```

Use the deployed CloudFront origin for `AllowedOrigin`. For local cloud-mode testing, use `http://localhost:5173` and set the matching callback and logout URLs.

The stack outputs the four values needed by the frontend:

```text
ApiUrl
UserPoolId
UserPoolClientId
CognitoLoginDomain
```

Create users from the Cognito console or with the administrative CLI. Self-registration is disabled.

## Frontend environment

```dotenv
VITE_JOB_DATA_SOURCE=api
VITE_AUTH_MODE=cognito
VITE_JOBS_API_URL=https://example.execute-api.ca-central-1.amazonaws.com
VITE_COGNITO_DOMAIN=https://example.auth.ca-central-1.amazoncognito.com
VITE_COGNITO_CLIENT_ID=example
VITE_COGNITO_REDIRECT_URI=http://localhost:5173/auth/callback
VITE_COGNITO_LOGOUT_URI=http://localhost:5173/jobs
```

Keep the default values (`mock` and `disabled`) for local CSV development.
