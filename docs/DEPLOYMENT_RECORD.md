# Deployment record

Date: 20 October 2026. Region: Mumbai (`ap-south-1`).

Both CDK stacks deployed successfully: `FinOpsData` and `FinOpsApplication`.

MFA policy update: the owner requested that MFA not be mandatory. CDK now deploys `OPTIONAL`; the live Cognito configuration was verified as `OPTIONAL` with software-token support retained, and `FinOpsData` returned `UPDATE_COMPLETE`. New users can sign in without authenticator enrollment after verifying their email. Existing users' enrolled MFA preferences are preserved. Five infrastructure assertions, type checking and strict synthesis passed for this update.

The final CDK release completed successfully. It retains the existing cross-stack log-bucket export, disables legacy edge query-string logging, and enables injected Athena partitions requiring explicit tenant, connection and snapshot filters. The repeated public HTTP smoke checks passed after this release.

Application: **https://d3uun3y7jmy2gy.cloudfront.net**

The public frontend returned HTTP 200. The auth configuration returned Cognito mode; an unauthenticated connection request returned 401. Starting sign-in returned a Cognito redirect with S256 PKCE, a random state and a Secure HttpOnly browser-binding cookie. No real customer account, billing data or model inference was used for those checks.

An isolated browser also verified the public secure-sign-in link and visible Cognito login form with no browser JavaScript errors. The first public GitHub Actions validation passed, including backend tests, browser workflows, dependency packaging and infrastructure checks. Encrypted management CloudTrail reports logging enabled with no delivery error.

The data-stack recovery preserved/imported the five retained resources and corrected CloudTrail KMS permissions. No database, bucket, key or user pool was deleted. The final release also narrows application S3 access to billing/evidence/report prefixes so the management CloudTrail archive is outside runtime object access.

The local application is available at http://127.0.0.1:8000 with an empty real workspace state. Local synthetic tenant/connection counts are zero. Create your own workspace and onboard the real AWS account using either the IAM role or access-key option.

Bedrock remains disabled at the operator level until its published guardrail, model entitlement, restricted invocation IAM and evaluation gates are completed. The account's Lambda concurrency quota is 10; a larger rollout requires quota/load acceptance. Customer sign-in and customer-authorized billing collection remain interactive acceptance steps; MFA enrollment is optional. See [DEPLOYMENT.md](DEPLOYMENT.md).

The public source repository is [nishantrishav01/finops-autopilot](https://github.com/nishantrishav01/finops-autopilot). Private deployment resource identifiers and generated outputs stay local under `.cache/`.
