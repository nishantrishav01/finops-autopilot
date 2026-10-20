# Connect customer cloud accounts

Create one application workspace per client. Register each AWS account, Azure subscription or GCP project within that workspace. Registration remains **PENDING** until an explicitly requested collection verifies access. A successful billing read is not a complete IAM permission audit.

## AWS: IAM role

1. Choose **Live connection → IAM role (recommended)**.
2. Enter the 12-digit customer account ID, region (Mumbai by default), and a customer-owned role ARN. In the cloud deployment the role name must begin `FinOpsAutopilotReadOnly` and must not have an IAM path.
3. Register the connection. Open its details and copy the generated **external ID** and **collector principal**. The principal is the deployed collector's IAM role, not the API role or an account-wide root principal. Locally, use the authorized operator's exact IAM principal.
4. In the customer account, trust that exact principal for `sts:AssumeRole` with `StringEquals` on `sts:ExternalId` equal to this connection's generated value. Never reuse an external ID between customers. The collector requests a 15-minute session.
5. Grant only the billing operations below; do not attach AdministratorAccess or a broad resource-management policy.
6. Press **Verify & collect billing**. STS identity must match the registered account before any billing query.

Required billing operations are Cost Explorer `GetCostAndUsage`, and Cost Optimization Hub `ListRecommendationSummaries` and `ListRecommendations`. STS `GetCallerIdentity` verifies account identity. Cost Optimization Hub must be enrolled by the customer first; unavailable COH produces an explicit partial result rather than fabricated savings. Cost Explorer must be enabled and may charge per request.

IAM action/resource mappings should be generated and reviewed using the AWS IAM Policy Autopilot tool. From the project root:

```powershell
uvx iam-policy-autopilot@latest generate-policies "$((Get-Location).Path)/services/api/connectors.py" --region ap-south-1 --service-hints sts ce cost-optimization-hub --pretty
```

Treat generated output as an analysis baseline: compare the chosen role/key branch, customer account and actual service-supported resource restrictions. Do not upload the entire generated policy to the platform role. CDK grants platform storage access to project resources, and only the collector can assume named customer roles.

## AWS: access key and secret key

1. Choose **Access key and secret key** in the same wizard.
2. Enter a dedicated billing-reader access key and secret key. For temporary `ASIA…` credentials also supply the session token.
3. Credentials are submitted to a separate administrator-only, write-only endpoint. Connection metadata contains only an opaque credential version and configured/pending status. HTTP validation errors never echo submitted values.
4. Locally the server encrypts credentials with **Windows CurrentUser DPAPI** and connection-specific entropy. Only the same Windows identity can decrypt them. Keep the application folder and Windows account protected; use disk encryption for SQLite billing data. Linux local access-key storage is intentionally unavailable; use role authentication there.
5. In AWS, Secrets Manager stores one secret per tenant/connection under `finops/…`, encrypted with the project KMS key. Only the collector role can read secret values. The API can create/write versions but cannot read them. A database pointer pins the active version so a failed metadata commit cannot silently replace a collector's credentials.
6. Keys are held only in server memory during use. They are never sent to Bedrock or stored in browser localStorage/sessionStorage.
7. Use **Connection details → Save or rotate access keys** to replace credentials. Temporary credentials expire and must be replaced before collection. Rotate the actual IAM key in the customer account; saving a new value in this app does not revoke an old AWS key.

Do not use root access keys, paste credentials into GitHub issues, commit `.env` files, enable SDK HTTP wire logging, or put secrets into account names/source imports. Only read APIs are called, but a supplied identity could possess broader permissions; audit it in the customer account.

## Billing behavior

AWS collects the preceding 90 completed days of amortized costs, grouped by service, scoped to the account. Credits/refunds are excluded from this view. This is not invoice reconciliation. Cost Explorer runs through its `us-east-1` service endpoint, even though the application is hosted in Mumbai. AWS role authentication and AWS billing-control-plane requests therefore do not imply India-only processing of every provider API.

The initial cloud deployment retains the top 40 COH recommendations per account, ordered by their individual source savings. It stores the complete provider-deduplicated account summary separately. Individual recommendations can overlap and must not be summed. Larger recommendation portfolios require a staged publication design before increasing this limit; it preserves DynamoDB's atomic transaction boundary.

## Azure

Enter the subscription UUID and Entra directory UUID. Grant the runtime identity **Cost Management Reader** and subscription read access at the intended subscription. The adapter uses `DefaultAzureCredential`, verifies subscription and directory, then reads actual pre-tax daily costs. In a local trusted environment use an authenticated Azure CLI or configured federation. In Lambda, configure customer-specific federation/runtime identity before enabling collection; this deployment does not create Entra identities. Native Azure Advisor ingestion and detailed telemetry are not implemented; verified source recommendations can be imported.

## Google Cloud

Enter project ID, billing account ID and `project.dataset.table` for a **standard usage billing export**. Enable that export in the customer's billing account first. Grant **BigQuery Job User** on the query project and **BigQuery Data Viewer** on the export dataset. Configure ADC locally or workload identity federation for the runtime. The query is parameterized and filters both project and billing account, including credits. Each query has a 1 GiB billed-byte cap. Empty results are rejected so mismatched scopes are not represented as connected. Native Recommender ingestion and detailed telemetry are not implemented.

## Import mode

All providers accept UTF-8 billing CSV with the header `date,service,amount,currency`, up to 10,000 rows / 1.8 MB text, using completed billing dates. Aggregate duplicate date/service/currency combinations first. Each import atomically replaces the active billing snapshot for that connection. Input validation failure preserves the previous snapshot. Source recommendation JSON imports require the customer's verified fields; blank template fields must be filled rather than treated as actual evidence.

No live collection or cloud resource modification happens automatically at registration. Provider reads and BigQuery queries can incur charges.
