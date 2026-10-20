# Dependencies and build inventory

## Toolchain

| Component | Version / source | Purpose |
|---|---|---|
| Python | 3.12 | API and Lambda runtime |
| Node.js | 24 | Frontend and CDK tooling |
| React / React DOM | 19.2.0 | Interface |
| TypeScript | 5.9.3 | Frontend and infrastructure type checks |
| Vite | 7.3.7 | Frontend bundling |
| FastAPI / Starlette | 0.149.0 / 1.9.0 | API and middleware |
| boto3 | 1.43.115 | AWS billing, storage and identity |
| azure-identity | 1.26.0 | Azure runtime credential chain |
| google-cloud-bigquery | 3.46.2 | GCP billing export reads |
| Mangum | 0.21.0 | API Gateway to ASGI adapter |
| aws-cdk-lib / CLI | 2.273.0 / 2.1146.0 | Infrastructure authoring/deployment |
| constructs | 10.8.1 | CDK construct model |
| cdk-nag | 2.38.2 | Pinned v2 rule/suppression API |
| Playwright | 1.56.1 | Desktop/mobile workflows |
| pytest / Moto | 9.1.1 / 5.1.16 | Backend and isolated AWS transaction tests |

`apps/web/package-lock.json` and `infra/package-lock.json` lock JavaScript transitive dependencies. Python manifests separate local/core, cloud SDK, Lambda packaging and test-emulator dependencies. `requirements-local.lock.txt` records the earlier local environment; use the current manifests and `requirements-lambda.lock.txt` for the cloud bundle rather than assuming that older inventory describes the cloud runtime.

The frontend uses Lucide icons and self-hosted DM Sans/Manrope fonts. It does not call a remote font CDN. Inspect dependency licenses before redistributing; publishing this repository does not relicense third-party packages.

## Setup and builds

Windows local setup: `scripts/setup.ps1` creates `.venv`, installs cloud-capable API dependencies, runs `npm ci` for the web app and builds it. `scripts/start.ps1` binds the API to loopback. Direct API development can use uvicorn; the production Lambda adapter uses Mangum.

`scripts/package-lambda.ps1` installs Linux x86_64 Python 3.12 binary wheels into an ignored build directory, copies only `services/`, excludes compiled caches from the CDK asset, and checks the uncompressed Lambda asset limit. No Docker installation is required for this ZIP deployment. Python modules containing real customer credentials or local databases are never copied into that directory.

The deployment includes Azure and GCP SDKs, but their runtime identities still require provider federation configuration. Installing an SDK is not equivalent to onboarding a cloud identity.

## Dependency review

Use `npm audit --prefix apps/web`, `npm audit --prefix infra`, and `pip-audit` against the intended Python runtime lock. Review findings and update the relevant exact pins plus lock files together; rerun adapter, concurrency, security and browser tests before deployment. Do not install unreviewed major-version upgrades in production or copy platform-specific Windows wheels into Lambda. Native libraries must use compatible Linux wheels.

GitHub Actions validates builds/tests and synthesis. It does not store cloud access keys or automatically deploy unreviewed pull requests. Production deployment requires an authenticated operator or an explicitly configured short-lived OIDC deployment role.
