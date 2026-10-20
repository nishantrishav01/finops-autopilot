# Project guide

## Repository layout

| Path | Responsibility |
|---|---|
| `apps/web/src/main.tsx` | Navigation, dashboards, account wizard, reviews, reports |
| `apps/web/src/ai.tsx` | Client AI consent, evidence references and advisory UI |
| `apps/web/src/client.ts` | Same-origin API client; no browser token/secret storage |
| `services/api/main.py` | API contracts, authorization, jobs and collection publication |
| `services/api/store.py` | Local SQLite and repository dispatch |
| `services/api/cloud_store.py` | DynamoDB atomic units and S3 snapshots |
| `services/api/cloud_auth.py` | Cognito PKCE and server-side sessions |
| `services/api/vault.py` | DPAPI / Secrets Manager write-only onboarding vault |
| `services/api/connectors.py` | Read-only AWS, Azure and GCP collectors |
| `services/api/domain.py` | Exact financial calculations and evidence gates |
| `services/api/advisor.py` | Bedrock governance, minimized prompts and validation |
| `services/api/lambda_handler.py` | Mangum, workflow worker and stream dispatcher |
| `infra/` | CDK stacks, locked dependencies and infrastructure assertions |
| `scripts/` | Setup, launcher, Lambda build and cost/preflight tools |
| `tests/` | Isolated backend fixtures and regression/security tests |
| `apps/web/e2e/` | Browser workflows and documentation screenshots |

## API groups

| Group | Operations |
|---|---|
| `/v1/auth/*`, `/v1/me` | Local or Cognito sign-in, logout and current membership |
| `/v1/connections` | Tenant-scoped cloud registration |
| `/v1/connections/{id}/credentials` | Administrator-only write-only AWS key storage/rotation |
| `/v1/connections/{id}/sync` | Queue a real read-only collection |
| `/v1/connections/{id}/import` | Validate and replace billing CSV snapshot |
| `/v1/connections/{id}/recommendations` | Import a verified source estimate |
| `/v1/jobs/{id}` | Persisted collection/assessment/advisory state |
| `/v1/overview` | Currency/provider/date-filtered spend and source coverage |
| `/v1/recommendations/*` | Evidence details, assessment, plan review and guidance |
| `/v1/ai/*` | Client governance, runtime fingerprint and usage limits |
| `/v1/reports/*`, `/v1/audit`, `/v1/policy` | Reports, audit records and evidence-age policy |

Do not accept tenant IDs from form/query bodies as an authorization shortcut. Cloud provider account IDs identify billing scopes; they do not identify application membership. Azure directory IDs are provider configuration, separate from the application tenant.

## First real AWS onboarding

Create a workspace, register a live AWS account with either authentication method, finish the customer IAM setup, then press Verify & collect billing. Check the account ID, source coverage, warnings, last successful collection time and recommendation limits. A financial total is meaningful only after collection; pending/empty accounts are not proof of zero actual cloud spend.

Select an opportunity, inspect source evidence, run the deterministic assessment, gather missing telemetry and owner approvals, and record a plan review. This app does not collect all performance metrics or execute the change. The customer performs approved changes through its own change process and independently validates outcomes.
