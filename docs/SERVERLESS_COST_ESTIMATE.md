# FinOps Autopilot serverless monthly cost estimate

As of 20 October 2026. Selected design: DynamoDB on-demand for operational data; S3 and Athena for billing analytics. Mumbai is the platform region, with global Opus inference only for individually approved clients.

This is a usage-based planning model, not a measured AWS bill or an AWS quotation. It was prepared before infrastructure creation. The project now includes the DynamoDB/S3 serverless implementation; [DEPLOYMENT.md](DEPLOYMENT.md) records its deployment and operating limits. The model includes three environment accounts and assumed customer/AI usage; it is not the bill for the initial single-account deployment, which starts with inference disabled. Cognito Plus and the actual security/retention settings should be reconciled with measured usage before revising the budget.

## Monthly totals

| Scenario | Customers | Cloud scopes | New paid AI calls/month | Platform USD before tax | INR with illustrative tax | Monthly INR budget including contingency |
|---|---:|---:|---:|---:|---:|---:|
| Pilot | 10 | 30 | 1,500 | $294.74 | INR 31,300.90 | INR 39,126.12 |
| Growth | 50 | 150 | 15,000 | $1,326.38 | INR 140,861.83 | INR 176,077.28 |
| Scale | 100 | 300 | 60,000 | $4,310.62 | INR 457,787.75 | INR 572,234.69 |

INR conversion uses **90 INR/USD as an editable planning assumption, not a current FX quote**. Tax is an illustrative 18% cash-budget assumption; Marketplace/seller/GSTIN treatment may differ. The recommended budget adds 25% contingency after illustrative tax. Contingency is not an AWS charge and is not a spending cap. Actual invoices determine tax and FX. [AWS India tax information](https://aws.amazon.com/tax-help/india/).

Annual steady-state budgets are INR 469,513.45, INR 2,112,927.41, INR 6,866,816.29 for Pilot, Growth and Scale respectively. These assume the same usage every month, without customer ramp, inflation or changing rates.

## What the platform total includes

| Monthly component, USD before tax | Pilot | Growth | Scale |
|---|---:|---:|---:|
| Application | $5.99 | $29.24 | $63.15 |
| Data | $15.23 | $76.15 | $152.30 |
| Security | $39.09 | $69.45 | $111.90 |
| Operations | $42.25 | $118.25 | $229.50 |
| AI | $80.18 | $801.76 | $3,207.02 |
| Development and staging allowance | $25.00 | $75.00 | $150.00 |
| AWS Business Support+ across three accounts | $87.00 | $156.54 | $396.75 |
| Total before illustrative tax | $294.74 | $1,326.38 | $4,310.62 |

- Application: API Gateway REST, Lambda API and collectors, Step Functions Standard, SQS, EventBridge Scheduler, CloudFront India delivery, API/report egress and Route 53 hosted zone.
- Data: DynamoDB reads/writes, table/index storage, point-in-time recovery and one additional full backup; retained S3 storage and requests; Athena scans; Glue standard ETL and catalog usage.
- Security: enterprise Cognito federation, two WAF ACLs and ten total rules, Secrets Manager, five KMS key versions and API usage. A monitoring allowance covers variable GuardDuty/Security Hub/scanning charges.
- Operations: CloudWatch ingestion, retained logs, custom metrics and alarms; allowances for CI/CD, CloudTrail, SES/SNS, tracing/query usage and additional India recovery copies.
- AI: Opus input/output, content/PII/denied-topic guardrail filters and AI worker compute/requests.

The named allowances are planning reserves, not independently priced service configurations: security USD 10/30/60, other operations USD 10/25/50, additional recovery USD 15/40/80, and combined development/staging USD 25/75/150. Replace them with service-specific quantities before purchase.

Support assumes one production and two nonproduction AWS accounts, each enrolled in Business Support+. The model uses the published per-account minimum and percentage tiers, including Bedrock usage in the support base. It does not deduct promotional credits. Consolidated-billing support discounts and another support choice would change the result. [AWS Support pricing](https://aws.amazon.com/premiumsupport/pricing/).

## Usage assumptions

- Each customer has one AWS account, one Azure subscription and one GCP project. Each scope is collected daily for 30 days.
- Paid, uncached AI requests per customer per day: five Pilot, ten Growth and twenty Scale. Assume every modeled customer has explicitly approved the selected global processing route.
- Average AI request: 4,000 input tokens and 1,500 total billed output tokens, including reasoning. Average AI Lambda duration is 30 seconds at 0.5 GB. These are assumptions; no real Bedrock response has yet established token use or latency.
- No prompt-cache discount, batch discount, negotiated discount, free allowance, new-account credit or Savings Plan reduction is deducted. On-demand gross pricing is intentionally conservative.
- Each customer generates 20,000 API calls and 20,000 CloudFront requests per month. The API uses 0.5 GB for 0.25 seconds on average. Collection workers use an aggregate 60 GB-seconds across five invocations per collection.
- DynamoDB uses a blended allocation of 20 billed read units and five billed write units per frontend API request, covering background jobs, index and transaction overhead. Measure item sizes, index amplification and worker operations during the pilot; these ratios are not AWS guarantees.
- Retained DynamoDB table/index storage: 1 GB per customer. PITR and one full additional backup are priced. Retained S3: 5 GB per cloud scope, including the assumed source versions, reports and evidence. This is the total retained balance, not an amount added every month.
- Athena: 0.05 billed TiB scanned per customer per month. Use partitioned compressed data and precomputed dashboard aggregates; do not scan the whole history for every page view. Per-query billing minimum/rounding and scan volume must be measured.
- CloudWatch: 0.5 GB ingested per customer per month with six 30-day months retained at steady state. This budget assumption does not itself establish compliance with a log-retention obligation.
- Guardrails: 12,000 evaluated input characters and 6,000 evaluated output characters per call, rounded separately to 1,000-character text units. Content filtering, sensitive-information filtering and denied topics are priced. No separate prompt-attack charge is added to content filtering, and no grounding/Automated Reasoning/evaluation/RAG service is assumed.
- Baseline networking uses Lambda without customer VPC attachment and public regional AWS APIs over TLS. There is no NAT Gateway, interface endpoint, static outbound IP or provisioned concurrency charge in this baseline. Add the relevant network configuration if customer requirements demand it.

## AI price and sensitivity

The AWS pricing page global Opus 5.5 table and its public rate data show **USD 4 per million input tokens and USD 20 per million output tokens** for the Mumbai request source. The model uses Standard on-demand inference and no caching benefit. [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), [public rate data](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrockfoundationmodels/USD/current/bedrockfoundationmodels.json).

At the assumed token lengths, model inference alone is USD 0.0460 per call. Guardrail filtering and worker/orchestration costs are additional.

An additional 1,000 billed output tokens on every request adds USD 30.00, USD 300.00, USD 1,200.00 per month in model charges for Pilot, Growth and Scale, before any extra guardrail text, worker time, support, tax or FX. A 25% contingency does not cover every possible token-length or traffic increase.

The Scale case has higher AI use per customer than Growth. Its higher per-customer budget is therefore not a like-for-like database scaling comparison. The current local default daily token reservation may block the Growth/Scale request volume; a client administrator would need an appropriately reviewed reservation limit, and the production gateway needs monetary admission controls.

## Customer-side and excluded charges

Customer-side Cost Explorer pages are priced separately at USD 0.01 per paginated request. At the assumed two pages per daily AWS scope collection this is USD 6.00, USD 30.00, USD 60.00 per month across the modeled customer accounts, separate from the platform total. Additional pages or refreshes increase this. [Cost Explorer pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/).

GCP BigQuery analysis/export storage and any GCP/Azure outbound data transfer are not included in the AWS platform bill. They depend on the customer dataset location, billed bytes, capacity agreement, existing allowances and result sizes. The current GCP collector sets a 1 GiB maximum billed-bytes limit per query; this does not cap query count or export-storage/network charges. Quote these from each customer configuration. [BigQuery pricing](https://cloud.google.com/bigquery/pricing).

Also excluded: normal customer cloud workload bills; engineering/migration labour; penetration testing, legal review and compliance certification; enterprise identity-provider licences; domain registration; paid Marketplace WAF rules; dedicated per-client accounts/keys; a full warm standby; and requirements beyond the listed allowances. Initial data backfill, retries and cutover tests can exceed the steady-state month. No numeric one-time implementation fee is asserted without scope and labour rates.

## Cost controls before deployment

1. Keep model calls explicitly requested; reuse current-context drafts and enforce tenant and platform quotas. Never silently retry an uncertain paid inference.
2. Limit daily collection frequency and maintain incremental snapshots. Reuse billing exports where suitable rather than repeatedly querying historical ranges.
3. Bound Athena scanned bytes by workgroup/query, use partitioned Parquet and materialize dashboard totals. Add byte/query limits for customer-side BigQuery.
4. Keep DynamoDB access key-based, cap scans, monitor consumed units and indexes, and use S3 for large payloads.
5. Measure actual tokens, Lambda duration, billed database units, data retention, scans and egress in staging. Recalculate before production approval.
6. Set per-client budgets, anomaly alerts, queue/concurrency limits and an operator AI kill switch. Billing alerts alone are not a hard spending cap.

## Workbook and verification

Open the accompanying editable workbook and change the numeric scenario selector on Inputs and Rates: 1 Pilot, 2 Growth or 3 Scale. Blue cells are editable. One active calculation feeds Monthly Cost; Sources maps rate references to public URLs. Editing usage, rates, tax or FX recalculates the selected scenario.

The three scenarios were reconciled to independent Decimal calculations. A zero-production-AI boundary was checked and no formula errors were found. The workbook was rendered for visual inspection. Native desktop Excel execution was not performed. The public price-list SKU/rate codes and retrieved dates are retained in the workbook and cost-model JSON. Refresh rates before purchase; actual AWS invoices may differ from this model.
