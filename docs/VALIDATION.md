# Validation record — 20 October 2026

Validated in the Windows workspace with Python 3.12 and Node.js 24. These are implementation checks, not a customer compliance certification.

| Check | Result |
|---|---|
| Backend/domain/connector/Bedrock/credential/DynamoDB tests | **68 passed** |
| Desktop and mobile workflows | **12 passed**, including real-account onboarding forms |
| CDK infrastructure security assertions | **5 passed** |
| TypeScript and Vite build | Passed |
| CDK strict synthesis / security rules | Passed with documented construct-specific exceptions |
| Frontend and infrastructure npm audits | No known vulnerabilities reported |
| Pinned Linux Lambda dependency audit | No known vulnerabilities reported |
| Local synthetic data cleanup | Zero synthetic tenants and connections after migration |
| Public source staging check | No blocked private/generated files or recognized credential patterns |

The subsequent targeted desktop/mobile onboarding run also passed after waiting for the dashboard to finish loading before documentation screenshots. An earlier browser failure exposed a stale review submission during an active assessment; the UI now blocks review submission while a background operation is active, and the full workflows passed after that correction.

## What was checked

New workspaces start empty; the production demo route and sample connection mode are unavailable. The previous synthetic tenant and explicitly marked synthetic local connections are removed while preserving real records. Test fixtures and routes exist only in the isolated test harness and are not packaged with Lambda.

Both AWS authentication methods are visible in the wizard. Access keys are masked/write-only, encrypted with DPAPI locally, absent from API responses/audit data/browser localStorage, and scoped to an authorized tenant administrator. Temporary credentials require a session token. AWS identity/account scope, Cost Explorer pagination, Azure subscription/directory checks and GCP project/billing-account filtering are tested with SDK stubs or mocks.

DynamoDB repository tests run in Moto, not live AWS. They establish tenant-scoped keys, atomic conflicting updates, collection phantom detection, rollback on transaction-size limits, S3 payload offloading and bounded transaction actions for collection queries. CDK assertions establish encrypted/protected storage, optional Cognito MFA, Standard workflow/stream failure handling, disabled initial Bedrock invocation, no request-body tracing and CloudTrail's exact-source-ARN key policy.

Financial and advisory tests cover Decimal accuracy, currency isolation, import replacement, review version checks, evidence-based approval blocking, CSV formula protection, per-client global-processing approval, minimized facts, schema/reference/action validation, quota reservations and changed-context rejection. Browser fixture advice is not a real model output or evidence of semantic quality.

## Cloud acceptance

The original CloudTrail creation failure was corrected and the five retained data resources were imported without deleting the database, buckets, key or user pool. The data stack then deployed successfully. Final application-stack status and HTTP smoke results belong in [DEPLOYMENT_RECORD.md](DEPLOYMENT_RECORD.md).

No customer billing collection, real Bedrock inference or customer MFA enrollment was performed by these tests. Model entitlement, the published guardrail and customer IAM grants still require acceptance. The initial cloud deployment disables Bedrock inference and includes no invocation IAM grant. The account's Lambda concurrency quota is 10; load acceptance and an appropriate quota increase remain required for a larger rollout.

## Reproduce

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
npm run build
npm --prefix apps/web run test:e2e
npm --prefix infra run test
npm --prefix infra run synth
```

Browser tests use port 8010, an isolated database/vault under `.cache/`, and a separate headless Chrome profile. Screenshots in `docs/images/` show empty documentation workspaces; transient fixture screenshots/traces remain ignored under `artifacts/`. The Starlette/httpx test adapter emits a deprecation warning; a future test-tool update should migrate that adapter. No cloud workload mutation is implemented or tested.
