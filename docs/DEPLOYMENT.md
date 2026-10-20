# Deployment and operations

## Initial deployment

The target is Mumbai (`ap-south-1`) in the AWS account selected by your authenticated CLI profile. The repository contains no deployment access keys or fixed customer account ID. Confirm the identity with `aws sts get-caller-identity` before each release.

Use Python 3.12, Node.js 24, AWS CLI v2 and the repository-pinned CDK CLI. Install the local dependencies first. The account/Region must have a compatible, protected `CDKToolkit` bootstrap stack. If it does not exist, an authorized administrator must run `npx cdk bootstrap aws://ACCOUNT_ID/ap-south-1` with an appropriate CloudFormation execution policy. Never delete a shared bootstrap stack.

```powershell
.\scripts\setup.ps1
npm ci --prefix infra
.\scripts\package-lambda.ps1
cd infra
npx cdk synth --strict
npx cdk diff
npx cdk deploy --all --strict --outputs-file ../.cache/deployment-outputs.json
```

Review the diff before deployment. Outputs identify the application URL, API URL, collector role, DynamoDB table and analytics bucket. Generated outputs are ignored and must not be committed to the public repository. Open the application URL and choose secure sign-in; Cognito verifies your email and enrolls TOTP MFA. Each new identity gets an empty workspace. No sample account or billing is created.

`FinOpsData` and `FinOpsApplication` use termination protection. Stateful resources use retention; DynamoDB has point-in-time recovery, customer-managed encryption and deletion protection. Bucket versioning protects analytics objects. Retention is not a cross-region backup or a tested disaster recovery plan.

## Initial account quota

The initial target account reported **10 total Lambda concurrent executions**. The CDK deployment therefore uses the shared account pool and does not reserve concurrency that would violate AWS's required unreserved capacity. API Gateway throttles requests; the workflow backs off on Lambda service/throttle rejections before invocation. This remains an initial-cohort deployment, not evidence that a 100-customer load is supported.

Before a broader rollout, request an appropriate Lambda concurrency quota, reserve API capacity, cap collector/advisory concurrency, load-test realistic billing portfolios, and validate queue age and service quotas. Avoid blindly retrying an uncertain paid model call.

## Release checks

Run backend tests, frontend build, desktop/mobile workflows, CDK assertions and strict synthesis. Confirm no secrets, databases, cloud outputs or private customer exports are staged in Git. `cdk diff` must show the intended change without replacement of stateful resources. Keep stable CDK construct IDs after deployment.

Smoke-test the public frontend, `/v1/auth/config`, an unauthenticated business route (401), and the Cognito redirect (state + PKCE + secure cookie). The operator/customer must complete a real interactive MFA sign-in and authorized billing collection to accept that integration; HTTP smoke tests do not prove customer IAM permissions, billing accuracy or customer-specific compliance.

## Cloud collection

Cloud functions set `FINOPS_ENABLE_LIVE=true`. Nothing collects automatically at registration. Follow [CONNECTORS.md](CONNECTORS.md), then explicitly verify and collect billing. Provider API/query charges may apply. Azure/GCP SDKs are packaged, but cross-cloud federated identities must be configured separately. No root keys or customer resource mutation permissions are required by the collector.

The API persists queued jobs in DynamoDB. Its stream dispatches a Standard workflow. The SQS dispatch-failure queue is retained for 14 days and alarmed. Alarms currently exist in CloudWatch without an email, pager or on-call subscription; configure an approved notification destination before operational handover. Application audit events and encrypted management CloudTrail support investigation, but privileged administrators can still change application records.

## Failure handling

Check the job error in the application first. SDK provider errors are redacted before persistence. Use CloudWatch request IDs and CloudFormation failure events for infrastructure diagnosis; never enable request-body or SDK wire logging with real credentials.

For dispatch failures, inspect the corresponding stream sequence/job ID, verify why dispatch failed, and start the workflow using the **same job ID** as execution name. Do not invent a new execution name to replay the same job. Standard execution idempotency and worker terminal-state checks prevent ordinary duplicate delivery from repeating work. After 23 hours of unsuccessful dispatch the stream failure destination is the operator's recovery source; the original job remains queued until reconciled.

An API/client timeout does not cancel a cloud job. Check persisted status before retrying. For an interrupted RUNNING job, inspect the Step Functions execution and provider activity before failing/retrying it. Workflow-level timeout/abort and a failure-recorder outage require operator reconciliation; do not leave these jobs running indefinitely. The initial release has no automatic recurring collection scheduler or customer cancellation endpoint.

If CloudFormation rolls back its first creation, retained resources can remain. Inventory this exact stack, preserve data, and import the retained resources into a repaired stack; do not blindly delete protected resources or deploy duplicates. The first deployment's CloudTrail failure was corrected by granting the CloudTrail service KMS use for its exact trail ARN, following [AWS CloudTrail KMS guidance](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-kms-key-policy-for-cloudtrail.html).

## Bedrock enablement

The deployed operator flag is disabled and no Bedrock invocation policy is attached by this initial stack. Before enabling, verify model availability/entitlement and global destination metadata, create and publish the required guardrail, restrict worker invocation permissions to the approved profile and backing model routes, run evaluations and a controlled paid canary, and release the pinned configuration through CDK. Do not simply add `bedrock:*`.

Every tenant still needs its own current administrator consent. India-only clients must remain blocked from the selected global Opus route. Deploying new IAM/configuration never substitutes for customer international-processing approval. See [BEDROCK_SETUP.md](BEDROCK_SETUP.md) and [BEDROCK_PRODUCTION_INDIA.md](BEDROCK_PRODUCTION_INDIA.md).

## Regulated production acceptance gates

- Use a customer domain and ACM certificate with an explicit modern CloudFront TLS policy. AWS's generated CloudFront hostname uses its default certificate policy; setting a minimum protocol property alone does not change it.
- Complete interactive Cognito MFA acceptance, session revocation/security review, enterprise federation and workspace invitation/role administration requirements.
- Route alarms to an agreed on-call channel; exercise incident handling, failure queue recovery and provider credential revocation.
- Load-test concurrency, DynamoDB conflict handling, portfolio sizes, active-snapshot dashboard latency and Athena scan limits.
- Define customer retention, deletion, log access and audit evidence policies; validate backup restores and the required recovery objectives.
- Complete customer-authorized live billing reconciliation and provider permissions review. Detailed workload telemetry remains necessary before approving many changes.
- Complete penetration testing, privacy/legal review and sector-specific requirements for each customer. This deployment is not a universal compliance certification.

The separate cost estimate is a workload planning model, not the actual AWS invoice for this initial account. Cognito Plus, WAF, KMS, logs, CloudTrail, S3, data retention, user activity and provider API requests affect actual charges even before Bedrock is enabled.
