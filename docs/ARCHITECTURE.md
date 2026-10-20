# Architecture and data boundaries

## Two runtimes

The trusted local edition uses FastAPI, loopback HTTP, SQLite and local background tasks. The AWS edition uses the same application/domain layer with a DynamoDB unit of work, immutable S3 analytics objects, Cognito authentication and durable Step Functions jobs. SQLite is never used as Lambda persistence.

CDK defines `FinOpsData` (KMS, DynamoDB, analytics/access-log buckets, Cognito and management CloudTrail) and `FinOpsApplication` (API, workers, workflow, stream dispatcher, SQS failure queue, CloudFront frontend, WAF, Glue/Athena and alarms). Stable construct IDs and retained resources protect stored data during code releases. Both stacks have termination protection. No EC2, Aurora, RDS Proxy, NAT gateway or always-running server is created.

## Operational data in DynamoDB

The key is `pk=TENANT#<server-derived-tenant>` and `sk=<kind>#<id>`. Operational kinds include connections, recommendations, jobs, audit events, evidence policies, AI policies, advice, usage reservations, report metadata and billing snapshot pointers. Reserved server scopes hold membership, hashed sessions and one-time OAuth state. Browser-supplied tenant identifiers are never accepted for authorization. Every endpoint derives the tenant from current membership; disabling membership takes effect on the next request.

Each write unit uses **one TransactWriteItems call**, checking versions of modified/read records and collection revision guards. Queries use strongly consistent reads and SDK pagination; collection guards prevent phantom inserts from bypassing duplicate-scope checks or quotas. Conflicts return 409 and require a refresh. Units exceeding 100 DynamoDB actions, approximately 3.8 MB serialized transaction size, or 350 KB per record fail before operational writes. The repository never silently chunks an atomic transaction.

The cloud collector retains up to 40 native recommendations per connection, preserving room to retire 40 old records and atomically publish 40 replacements with metadata/audit updates. User-provided source imports are individual transactions. Review and AI policy updates check source/governance versions and cannot silently overwrite concurrent changes.

## Billing analytics and evidence in S3

Billing rows are immutable JSONL objects under `curated/tenant=…/connection=…/snapshot=…/billing.jsonl`. DynamoDB stores the active snapshot pointer. Raw source payloads and report contents also reside in S3; DynamoDB holds their references and evidence hashes. The dashboard reads the active snapshots only, so history is not double counted. Failed metadata commits may leave unreferenced S3 objects; cleanup must compare active references before deleting anything.

Glue catalogs `finops_billing.billing_snapshots`; Athena workgroup `finops-billing` requires encrypted results and limits each query to 1 GiB scanned. This is an operator analytics surface, not a customer arbitrary-SQL API. Injected partition projection requires explicit `tenant`, `connection` and `snapshot` filters and maps them to the immutable S3 folder; no crawler or partition-registration job is needed. Operators must obtain the current snapshot from the server's active billing pointer. A blanket sum of multiple historical snapshots double counts billing. Parquet compaction and a customer query authorization service remain scale gates. Customers cannot directly access the shared catalog through the web app.

## Authentication

Cognito uses verified email, optional TOTP MFA, Plus-tier threat protection and authorization-code PKCE. A random five-minute state is browser-bound using a Secure HttpOnly SameSite=Lax cookie and atomically consumed before code exchange. Cognito verifies the access token server-side via GetUser. Tokens never reach browser JavaScript or persistent session storage. The browser receives a one-hour Secure HttpOnly SameSite=Strict opaque cookie; DynamoDB stores only its hash. TTL expiration is enforced in application logic without waiting for DynamoDB TTL deletion.

Local accounts use scrypt and eight-hour HttpOnly cookies over loopback HTTP. They are separate from Cognito users. Signing out revokes the application session; Cognito's own session may still support sign-in, subject to MFA/risk policy. Enterprise federation, invitations and delegated role-administration UI remain rollout work. Each self-registered cloud identity currently owns one new workspace.

## Durable jobs

The API commits a QUEUED job and audit record atomically. The DynamoDB stream acts as a transactional outbox. A dispatcher starts a Standard workflow using the unique job ID as execution name. Duplicate stream delivery does not start another execution. Failures retry on the stream and finally enter an encrypted SQS failure queue. The workflow invokes a bounded Lambda worker and records a failure if invocation fails. SDK throttling/service errors rejected before invocation may retry; paid AI calls and uncertain interrupted workers are not blindly replayed. A RUNNING job seen after an interrupted invocation is failed for explicit review.

Collections, evidence assessments and advisory calls share the durable mechanism. Workflow execution payloads contain tenant/job IDs only, not credentials or billing bodies. CloudWatch workflow logs exclude execution data; API access logs exclude request paths, bodies, cookies and query strings. Lambda timeouts, workflow-level termination and DLQ replay require the operator procedures in DEPLOYMENT.md. A recurring collection scheduler is not enabled in this release.

## Credentials and IAM

The API writes Secrets Manager versions but cannot read their values. The collector reads only project `finops/*` secrets and can assume customer roles named `FinOpsAutopilotReadOnly*`, with an application-generated external ID. Each worker/API has a dedicated IAM role. Runtime grants are scoped to project storage resources. Credentials are excluded from saved connection config, audits, source snapshots and model evidence. Local keys use Windows DPAPI; database billing data needs operating-system disk protection.

Tenant isolation is enforced by the shared application service; it is not a separate AWS account or CMK per client. Customers requiring dedicated-account, per-tenant KMS or sector-specific isolation need a separate deployment and acceptance review.

## Financial and AI controls

Amounts use Decimal and explicit currencies. Provider-deduplicated AWS savings are kept separate from individual overlapping estimates; Azure/GCP source estimates do not establish portfolio savings. No FX conversion, forecast guarantee or realized-savings claim is generated. Current dates come from runtime, not a hard-coded synthetic scenario.

Deterministic evidence policy gates plan review. Bedrock receives only minimized application-owned facts after provider, residency, governance fingerprint and quota checks. Global Opus routing is blocked unless the individual client administrator approves international processing. AI output passes schema/reference/action validation and human review; it cannot clear missing evidence or perform mutations. The initial CDK deployment disables inference and grants no Bedrock invocation permissions until a controlled enablement release.

## Security and rollout boundaries

WAF protects the regional API, including its default endpoint. CloudFront uses an OAC to a private frontend bucket. The initial AWS-generated CloudFront hostname uses AWS's default certificate/security policy; enforce a modern TLS minimum with a customer domain and ACM certificate before a regulated production rollout. Frontend assets are globally cached; that is separate from customer data residency. Management CloudTrail is encrypted and validated; application audit records remain mutable by privileged platform administrators. Object Lock, customer retention/deletion automation, incident notification routing, backup restore drills, penetration testing and customer-specific legal review are not compliance certifications supplied by this code.
