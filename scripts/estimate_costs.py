"""Reproducible planning estimate from cached public AWS catalogs, not an invoice."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import json
from pathlib import Path

DATE = '2026-10-20'
OUT = Path('outputs/finops-cost-estimate-2026-10-20')
D = lambda value: Decimal(str(value))
CATALOG = Path('.cache/pricing')

# One active scenario in the workbook; the report evaluates this same model for
# all three planning cases. These are assumptions, not observed customer usage.
DRIVERS = [
 ('customers','Customers','clients',[10,50,100]),
 ('aws_accounts','AWS accounts per customer','accounts',[1,1,1]),
 ('azure_accounts','Azure subscriptions per customer','subscriptions',[1,1,1]),
 ('gcp_accounts','GCP projects per customer','projects',[1,1,1]),
 ('users','Enterprise SSO users per customer','monthly active users',[10,10,10]),
 ('ai_daily','New paid guidance calls per customer per day','calls/day',[5,10,20]),
 ('input_tokens','Average billable input tokens per call','tokens',[4000,4000,4000]),
 ('output_tokens','Average billable output including reasoning','tokens',[1500,1500,1500]),
 ('api_requests','API requests per customer per month','requests',[20000,20000,20000]),
 ('api_seconds','Average API Lambda duration','seconds',[0.25,0.25,0.25]),
 ('api_memory','API Lambda allocated memory','GB',[0.5,0.5,0.5]),
 ('sync_daily','Collections per cloud scope per day','runs/day',[1,1,1]),
 ('worker_seconds','Total worker compute time per collection','seconds',[60,60,60]),
 ('worker_memory','Collection worker allocated memory','GB',[1,1,1]),
 ('worker_invocations','Worker invocations per collection','invocations',[5,5,5]),
 ('ai_seconds','Average AI worker duration including wait','seconds',[30,30,30]),
 ('ai_memory','AI worker allocated memory','GB',[0.5,0.5,0.5]),
 ('read_units','Billable DynamoDB read units per API request','RRU',[20,20,20]),
 ('write_units','Billable DynamoDB write units per API request','WRU',[5,5,5]),
 ('dynamo_gb','DynamoDB retained table and index storage per client','GB',[1,1,1]),
 ('s3_gb','Retained S3 storage per cloud scope including copies','GB',[5,5,5]),
 ('s3_put','Monthly S3 PUT/LIST requests per cloud scope','requests',[3000,3000,3000]),
 ('s3_get','Monthly S3 GET requests per customer','requests',[20000,20000,20000]),
 ('athena_tib','Athena billed scan volume per customer per month','TiB',[0.05,0.05,0.05]),
 ('glue_hours','Glue ETL compute per month','DPU-hours',[2,10,20]),
 ('glue_objects','Glue catalog objects retained','objects',[1000,5000,10000]),
 ('glue_requests','Glue catalog API requests per month','requests',[10000,50000,100000]),
 ('cf_gb','CloudFront India delivery per customer','GB/month',[2,2,2]),
 ('cf_requests','CloudFront HTTPS requests per customer','requests/month',[20000,20000,20000]),
 ('egress_gb','API/report internet egress per customer','GB/month',[0.5,0.5,0.5]),
 ('log_gb','CloudWatch log ingestion per customer','GB/month',[0.5,0.5,0.5]),
 ('log_retention','Steady-state CloudWatch retention','months',[6,6,6]),
 ('metrics','Custom CloudWatch metrics','metric-months',[40,100,180]),
 ('alarms','Standard CloudWatch alarms','alarm-months',[10,20,30]),
 ('secrets','Secrets Manager retained secrets','secrets',[5,10,15]),
 ('secret_calls','Secrets Manager API requests','requests/month',[10000,50000,100000]),
 ('kms_keys','Customer-managed KMS key versions','key-months',[5,5,5]),
 ('kms_calls','Symmetric KMS API requests','requests/month',[100000,500000,1000000]),
 ('waf_acls','WAF web ACLs: API and static frontend','ACL-months',[2,2,2]),
 ('waf_rules','Total WAF rules across both ACLs','rule-months',[10,10,10]),
 ('guard_input_chars','Characters evaluated by guardrail on input','characters/call',[12000,12000,12000]),
 ('guard_output_chars','Characters evaluated by guardrail on output','characters/call',[6000,6000,6000]),
 ('collection_steps','State transitions per collection','transitions',[8,8,8]),
 ('ai_steps','State transitions per guidance job','transitions',[6,6,6]),
 ('security_allowance','GuardDuty / Security Hub / scanning allowance','USD/month',[10,30,60]),
 ('operations_allowance','CI/CD, CloudTrail, SES/SNS, traces and query allowance','USD/month',[10,25,50]),
 ('dr_allowance','Additional India-region recovery copy allowance','USD/month',[15,40,80]),
 ('nonprod_allowance','Combined dev/staging usage and AI test allowance','USD/month',[25,75,150]),
 ('ce_pages','Paid Cost Explorer pages per AWS scope per collection','pages',[2,2,2]),
]


def catalog_rate(service, usage, begin='0', **filters):
    doc = json.loads((CATALOG/f'{service}.json').read_text())
    rows = []
    for sku, product in doc['products'].items():
        attrs = product['attributes']
        if attrs.get('usagetype') != usage or any(attrs.get(k) != v for k,v in filters.items()):
            continue
        for term in doc['terms']['OnDemand'].get(sku, {}).values():
            for price in term['priceDimensions'].values():
                if price['beginRange'] == begin:
                    rows.append((price, sku))
    if len(rows) != 1:
        raise ValueError(f'Expected one price: {service} {usage} {begin}; found {len(rows)}')
    price, sku = rows[0]
    region = '' if service in ('AmazonCloudFront','AmazonRoute53') else 'ap-south-1/'
    return {'value': price['pricePerUnit']['USD'], 'unit': price['unit'], 'source':
        f'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/{region}index.json',
        'sku': sku, 'publication': doc['publicationDate'], 'description': price['description']}


def rates():
    specs = [
      ('ddb_read','DynamoDB read request unit','AmazonDynamoDB','APS3-ReadRequestUnits','0'),
      ('ddb_write','DynamoDB write request unit','AmazonDynamoDB','APS3-WriteRequestUnits','0'),
      ('ddb_storage','DynamoDB storage','AmazonDynamoDB','APS3-TimedStorage-ByteHrs','25'),
      ('ddb_pitr','DynamoDB point-in-time recovery','AmazonDynamoDB','APS3-TimedPITRStorage-ByteHrs','0'),
      ('ddb_backup','DynamoDB on-demand backup storage','AmazonDynamoDB','APS3-TimedBackupStorage-ByteHrs','0'),
      ('lambda_compute','Lambda x86 compute','AWSLambda','APS3-Lambda-GB-Second','0'),
      ('lambda_request','Lambda invocation','AWSLambda','APS3-Request','0'),
      ('api_rate','API Gateway REST request','AmazonApiGateway','APS3-ApiGatewayRequest','0'),
      ('s3_storage','S3 Standard storage','AmazonS3','APS3-TimedStorage-ByteHrs','0'),
      ('s3_put_rate','S3 PUT/LIST request','AmazonS3','APS3-Requests-Tier1','0'),
      ('s3_get_rate','S3 GET request','AmazonS3','APS3-Requests-Tier2','0'),
      ('athena_rate','Athena SQL billed scan','AmazonAthena','APS3-DataScannedInTB','0'),
      ('glue_rate','Glue standard ETL DPU compute','AWSGlue','APS3-ETL-DPU-Hour','0'),
      ('glue_object_rate','Glue catalog object','AWSGlue','APS3-Catalog-Storage','0'),
      ('glue_request_rate','Glue catalog request','AWSGlue','APS3-Catalog-Request','0'),
      ('cf_storage_rate','CloudFront India outbound delivery','AmazonCloudFront','IN-DataTransfer-Out-Bytes','0'),
      ('cf_request_rate','CloudFront India HTTPS request','AmazonCloudFront','IN-Requests-Tier2-HTTPS','0'),
      ('egress_rate','Mumbai internet egress','AWSDataTransfer','APS3-DataTransfer-Out-Bytes','0'),
      ('log_rate','CloudWatch standard log ingestion','AmazonCloudWatch','APS3-DataProcessing-Bytes','0'),
      ('log_storage_rate','CloudWatch retained logs','AmazonCloudWatch','APS3-TimedStorage-ByteHrs','0'),
      ('metric_rate','CloudWatch custom metric','AmazonCloudWatch','APS3-CW:MetricMonitorUsage','0'),
      ('alarm_rate','CloudWatch standard alarm','AmazonCloudWatch','APS3-CW:AlarmMonitorUsage','0'),
      ('secret_rate','Secrets Manager retained secret','AWSSecretsManager','APS3-AWSSecretsManager-Secrets','0'),
      ('secret_api_rate','Secrets Manager API request','AWSSecretsManager','APS3-AWSSecretsManagerAPIRequest','0'),
      ('kms_key_rate','KMS key version','awskms','ap-south-1-KMS-Keys','0'),
      ('kms_api_rate','KMS symmetric request','awskms','ap-south-1-KMS-Requests','0'),
      ('waf_acl_rate','WAF web ACL','awswaf','APS3-WebACLV2','0'),
      ('waf_rule_rate','WAF rule','awswaf','APS3-RuleV2','0'),
      ('waf_request_rate','WAF request','awswaf','APS3-Request','0'),
      ('step_rate','Step Functions Standard transition','AmazonStates','APS3-StateTransition','0'),
      ('queue_rate','SQS standard request','AWSQueueService','APS3-Requests-Tier1','0'),
      ('schedule_rate','EventBridge scheduled invocation','AWSEvents','APS3-ScheduledInvocation','14000000'),
      ('zone_rate','Route 53 hosted zone','AmazonRoute53','HostedZone','0'),
      ('cognito_rate','Cognito enterprise federation MAU','AmazonCognito','APS3-CognitoEssentialsMAU','0'),
      ('guard_content','Guardrail content filter per text unit','AmazonBedrock','APS3-Guardrail-ContentPolicyUnitsConsumed','0'),
      ('guard_pii','Guardrail sensitive information per text unit','AmazonBedrock','APS3-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed','0'),
      ('guard_topics','Guardrail denied topics per text unit','AmazonBedrock','APS3-Guardrail-TopicPolicyUnitsConsumed','0'),
    ]
    result = {key:{'name':name, **catalog_rate(service,usage,begin)} for key,name,service,usage,begin in specs}
    table = json.loads((CATALOG/'bedrockfoundationmodels.json').read_text())['regions']['Asia Pacific (Mumbai)']
    for key,name,token in [('opus_input','Opus 5.5 global input per million tokens','Xcm0XjOuAU0qiyQp5FJ9l9UvyK71NzEH_EIrD22wjP4'),
       ('opus_output','Opus 5.5 global output per million tokens','ZyfvQTBZN4ZtDEiynK6bf69DmwsGmnRhbhVjfSdairE')]:
        record=table[token]
        result[key]={'name':name,'value':record['price'],'unit':'million tokens','source':'https://aws.amazon.com/bedrock/pricing/',
            'data_source':'https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrockfoundationmodels/USD/current/bedrockfoundationmodels.json',
            'sku':record['rateCode'],'publication':DATE,'description':'Global on-demand Standard tier, no cache or batch discount'}
    result['ce_rate']={'name':'Cost Explorer paid page','value':'0.01','unit':'paginated request',
        'source':'https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/','publication':DATE,'description':'Customer-side query charge, separate from platform bill'}
    return result


# Expressions are authored here, not accepted from customer input. The workbook
# translates the same transparent quantity calculations into cell references.
LINES = [
 ('API Gateway REST','Application','customers*api_requests','api_rate','requests'),
 ('API Lambda compute','Application','customers*api_requests*api_seconds*api_memory','lambda_compute','GB-seconds'),
 ('API Lambda requests','Application','customers*api_requests','lambda_request','requests'),
 ('Collection Lambda compute','Application','customers*(aws_accounts+azure_accounts+gcp_accounts)*days*sync_daily*worker_seconds*worker_memory','lambda_compute','GB-seconds'),
 ('Collection and workflow starter requests','Application','customers*(aws_accounts+azure_accounts+gcp_accounts)*days*sync_daily*(worker_invocations+1)','lambda_request','requests'),
 ('DynamoDB reads','Data','customers*api_requests*read_units','ddb_read','read units'),
 ('DynamoDB writes including index/transaction allowance','Data','customers*api_requests*write_units','ddb_write','write units'),
 ('DynamoDB retained storage','Data','customers*dynamo_gb','ddb_storage','GB-months'),
 ('DynamoDB point-in-time recovery','Data','customers*dynamo_gb','ddb_pitr','GB-months'),
 ('One additional full DynamoDB backup','Data','customers*dynamo_gb','ddb_backup','GB-months'),
 ('S3 retained billing, evidence and report storage','Data','customers*(aws_accounts+azure_accounts+gcp_accounts)*s3_gb','s3_storage','GB-months'),
 ('S3 PUT/LIST requests','Data','customers*(aws_accounts+azure_accounts+gcp_accounts)*s3_put','s3_put_rate','requests'),
 ('S3 GET requests','Data','customers*s3_get','s3_get_rate','requests'),
 ('Athena SQL scans','Data','customers*athena_tib','athena_rate','billed TiB'),
 ('Glue transformation / crawler compute','Data','glue_hours','glue_rate','DPU-hours'),
 ('Glue catalog storage','Data','glue_objects','glue_object_rate','object-months'),
 ('Glue catalog API','Data','glue_requests','glue_request_rate','requests'),
 ('CloudFront India delivery','Application','customers*cf_gb','cf_storage_rate','GB'),
 ('CloudFront HTTPS requests','Application','customers*cf_requests','cf_request_rate','requests'),
 ('API and report internet delivery','Application','customers*egress_gb','egress_rate','GB'),
 ('Cognito enterprise federation','Security','customers*users','cognito_rate','MAU'),
 ('WAF web ACLs','Security','waf_acls','waf_acl_rate','ACL-months'),
 ('WAF rules','Security','waf_rules','waf_rule_rate','rule-months'),
 ('WAF requests, API plus frontend','Security','customers*(api_requests+cf_requests)','waf_request_rate','requests'),
 ('Secrets Manager storage','Security','secrets','secret_rate','secret-months'),
 ('Secrets Manager requests','Security','secret_calls','secret_api_rate','requests'),
 ('KMS key versions','Security','kms_keys','kms_key_rate','key-months'),
 ('KMS requests','Security','kms_calls','kms_api_rate','requests'),
 ('CloudWatch log ingestion','Operations','customers*log_gb','log_rate','GB'),
 ('CloudWatch six-month retained log balance','Operations','customers*log_gb*log_retention','log_storage_rate','GB-months'),
 ('CloudWatch custom metrics','Operations','metrics','metric_rate','metric-months'),
 ('CloudWatch alarms','Operations','alarms','alarm_rate','alarm-months'),
 ('Step Functions Standard','Application','customers*(aws_accounts+azure_accounts+gcp_accounts)*days*sync_daily*collection_steps+customers*days*ai_daily*ai_steps','step_rate','transitions'),
 ('SQS send/receive/delete, including starter work','Application','3*(customers*(aws_accounts+azure_accounts+gcp_accounts)*days*sync_daily+customers*days*ai_daily)','queue_rate','requests'),
 ('EventBridge Scheduler','Application','customers*(aws_accounts+azure_accounts+gcp_accounts)*days*sync_daily','schedule_rate','invocations'),
 ('Route 53 zone','Application','1','zone_rate','zone-months'),
 ('Opus 5.5 input tokens','AI','customers*days*ai_daily*input_tokens/1000000','opus_input','million tokens'),
 ('Opus 5.5 output including reasoning','AI','customers*days*ai_daily*output_tokens/1000000','opus_output','million tokens'),
 ('Guardrail content filtering','AI','customers*days*ai_daily*(CEILING(guard_input_chars/1000,1)+CEILING(guard_output_chars/1000,1))','guard_content','text units'),
 ('Guardrail sensitive information filtering','AI','customers*days*ai_daily*(CEILING(guard_input_chars/1000,1)+CEILING(guard_output_chars/1000,1))','guard_pii','text units'),
 ('Guardrail denied topics','AI','customers*days*ai_daily*(CEILING(guard_input_chars/1000,1)+CEILING(guard_output_chars/1000,1))','guard_topics','text units'),
 ('AI Lambda compute','AI','customers*days*ai_daily*ai_seconds*ai_memory','lambda_compute','GB-seconds'),
 ('AI worker and starter requests','AI','customers*days*ai_daily*2','lambda_request','requests'),
 ('Security monitoring allowance','Security','security_allowance',None,'USD allowance'),
 ('CI/CD and other operational services allowance','Operations','operations_allowance',None,'USD allowance'),
 ('Additional India recovery copy allowance','Operations','dr_allowance',None,'USD allowance'),
]


def evaluate(expr, inputs):
    import re
    expr = re.sub(r'\b\d+(?:\.\d+)?\b',lambda m:f'D("{m.group()}")',expr)
    return D(eval(expr,{'__builtins__':{},'D':D,'CEILING':lambda value,unit:value.to_integral_value(rounding=ROUND_CEILING)},inputs))


def money(value):
    return f'{D(value).quantize(D(".01"),rounding=ROUND_HALF_UP):,.2f}'


def report(model):
    cases=model['cases']
    lines=['# FinOps Autopilot serverless monthly cost estimate', '',
      'As of 20 October 2026. Selected design: DynamoDB on-demand for operational data; S3 and Athena for billing analytics. Mumbai is the platform region, with global Opus inference only for individually approved clients.', '',
      'This is a usage-based planning model, not a measured AWS bill or an AWS quotation. No cloud resources were created. The local application still uses SQLite; production storage and workflow migration remain implementation work.', '',
      '## Monthly totals', '',
      '| Scenario | Customers | Cloud scopes | New paid AI calls/month | Platform USD before tax | INR with illustrative tax | Monthly INR budget including contingency |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for c in cases:
        t=c['totals'];i=c['inputs']; scopes=D(i['customers'])*(D(i['aws_accounts'])+D(i['azure_accounts'])+D(i['gcp_accounts']))
        lines.append(f"| {c['name']} | {i['customers']} | {scopes:,.0f} | {D(t['ai_calls']):,.0f} | ${money(t['pretax_usd'])} | INR {money(t['monthly_inr_with_tax'])} | INR {money(t['budget_inr_with_25pct_buffer'])} |")
    lines += ['', 'INR conversion uses **90 INR/USD as an editable planning assumption, not a current FX quote**. Tax is an illustrative 18% cash-budget assumption; Marketplace/seller/GSTIN treatment may differ. The recommended budget adds 25% contingency after illustrative tax. Contingency is not an AWS charge and is not a spending cap. Actual invoices determine tax and FX. [AWS India tax information](https://aws.amazon.com/tax-help/india/).', '',
      'Annual steady-state budgets are INR '+', INR '.join(money(c['totals']['annual_budget_inr']) for c in cases)+' for Pilot, Growth and Scale respectively. These assume the same usage every month, without customer ramp, inflation or changing rates.', '',
      '## What the platform total includes', '',
      '| Monthly component, USD before tax | Pilot | Growth | Scale |', '|---|---:|---:|---:|']
    for category in ['Application','Data','Security','Operations','AI']:
        amounts=[sum((D(r['cost']) for r in c['lines'] if r['category']==category),D(0)) for c in cases]
        lines.append('| '+category+' | '+' | '.join('$'+money(v) for v in amounts)+' |')
    for key,label in [('nonproduction_usd','Development and staging allowance'),('support_usd','AWS Business Support+ across three accounts'),('pretax_usd','Total before illustrative tax')]:
        lines.append('| '+label+' | '+' | '.join('$'+money(c['totals'][key]) for c in cases)+' |')
    lines += ['',
      '- Application: API Gateway REST, Lambda API and collectors, Step Functions Standard, SQS, EventBridge Scheduler, CloudFront India delivery, API/report egress and Route 53 hosted zone.',
      '- Data: DynamoDB reads/writes, table/index storage, point-in-time recovery and one additional full backup; retained S3 storage and requests; Athena scans; Glue standard ETL and catalog usage.',
      '- Security: enterprise Cognito federation, two WAF ACLs and ten total rules, Secrets Manager, five KMS key versions and API usage. A monitoring allowance covers variable GuardDuty/Security Hub/scanning charges.',
      '- Operations: CloudWatch ingestion, retained logs, custom metrics and alarms; allowances for CI/CD, CloudTrail, SES/SNS, tracing/query usage and additional India recovery copies.',
      '- AI: Opus input/output, content/PII/denied-topic guardrail filters and AI worker compute/requests.', '',
      'The named allowances are planning reserves, not independently priced service configurations: security USD 10/30/60, other operations USD 10/25/50, additional recovery USD 15/40/80, and combined development/staging USD 25/75/150. Replace them with service-specific quantities before purchase.', '',
      'Support assumes one production and two nonproduction AWS accounts, each enrolled in Business Support+. The model uses the published per-account minimum and percentage tiers, including Bedrock usage in the support base. It does not deduct promotional credits. Consolidated-billing support discounts and another support choice would change the result. [AWS Support pricing](https://aws.amazon.com/premiumsupport/pricing/).', '',
      '## Usage assumptions', '',
      '- Each customer has one AWS account, one Azure subscription and one GCP project. Each scope is collected daily for 30 days.',
      '- Paid, uncached AI requests per customer per day: five Pilot, ten Growth and twenty Scale. Assume every modeled customer has explicitly approved the selected global processing route.',
      '- Average AI request: 4,000 input tokens and 1,500 total billed output tokens, including reasoning. Average AI Lambda duration is 30 seconds at 0.5 GB. These are assumptions; no real Bedrock response has yet established token use or latency.',
      '- No prompt-cache discount, batch discount, negotiated discount, free allowance, new-account credit or Savings Plan reduction is deducted. On-demand gross pricing is intentionally conservative.',
      '- Each customer generates 20,000 API calls and 20,000 CloudFront requests per month. The API uses 0.5 GB for 0.25 seconds on average. Collection workers use an aggregate 60 GB-seconds across five invocations per collection.',
      '- DynamoDB uses a blended allocation of 20 billed read units and five billed write units per frontend API request, covering background jobs, index and transaction overhead. Measure item sizes, index amplification and worker operations during the pilot; these ratios are not AWS guarantees.',
      '- Retained DynamoDB table/index storage: 1 GB per customer. PITR and one full additional backup are priced. Retained S3: 5 GB per cloud scope, including the assumed source versions, reports and evidence. This is the total retained balance, not an amount added every month.',
      '- Athena: 0.05 billed TiB scanned per customer per month. Use partitioned compressed data and precomputed dashboard aggregates; do not scan the whole history for every page view. Per-query billing minimum/rounding and scan volume must be measured.',
      '- CloudWatch: 0.5 GB ingested per customer per month with six 30-day months retained at steady state. This budget assumption does not itself establish compliance with a log-retention obligation.',
      '- Guardrails: 12,000 evaluated input characters and 6,000 evaluated output characters per call, rounded separately to 1,000-character text units. Content filtering, sensitive-information filtering and denied topics are priced. No separate prompt-attack charge is added to content filtering, and no grounding/Automated Reasoning/evaluation/RAG service is assumed.',
      '- Baseline networking uses Lambda without customer VPC attachment and public regional AWS APIs over TLS. There is no NAT Gateway, interface endpoint, static outbound IP or provisioned concurrency charge in this baseline. Add the relevant network configuration if customer requirements demand it.', '',
      '## AI price and sensitivity', '',
      'The AWS pricing page global Opus 5.5 table and its public rate data show **USD 4 per million input tokens and USD 20 per million output tokens** for the Mumbai request source. The model uses Standard on-demand inference and no caching benefit. [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), [public rate data](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrockfoundationmodels/USD/current/bedrockfoundationmodels.json).', '',
      'At the assumed token lengths, model inference alone is USD '+format(D(4000)*D(4)/D(1000000)+D(1500)*D(20)/D(1000000),'.4f')+' per call. Guardrail filtering and worker/orchestration costs are additional.', '',
      'An additional 1,000 billed output tokens on every request adds USD '+', USD '.join(money(D(c['totals']['ai_calls'])*D('.02')) for c in cases)+' per month in model charges for Pilot, Growth and Scale, before any extra guardrail text, worker time, support, tax or FX. A 25% contingency does not cover every possible token-length or traffic increase.', '',
      'The Scale case has higher AI use per customer than Growth. Its higher per-customer budget is therefore not a like-for-like database scaling comparison. The current local default daily token reservation may block the Growth/Scale request volume; a client administrator would need an appropriately reviewed reservation limit, and the production gateway needs monetary admission controls.', '',
      '## Customer-side and excluded charges', '',
      'Customer-side Cost Explorer pages are priced separately at USD 0.01 per paginated request. At the assumed two pages per daily AWS scope collection this is USD '+', USD '.join(money(c['totals']['customer_ce_usd']) for c in cases)+' per month across the modeled customer accounts, separate from the platform total. Additional pages or refreshes increase this. [Cost Explorer pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/).', '',
      'GCP BigQuery analysis/export storage and any GCP/Azure outbound data transfer are not included in the AWS platform bill. They depend on the customer dataset location, billed bytes, capacity agreement, existing allowances and result sizes. The current GCP collector sets a 1 GiB maximum billed-bytes limit per query; this does not cap query count or export-storage/network charges. Quote these from each customer configuration. [BigQuery pricing](https://cloud.google.com/bigquery/pricing).', '',
      'Also excluded: normal customer cloud workload bills; engineering/migration labour; penetration testing, legal review and compliance certification; enterprise identity-provider licences; domain registration; paid Marketplace WAF rules; dedicated per-client accounts/keys; a full warm standby; and requirements beyond the listed allowances. Initial data backfill, retries and cutover tests can exceed the steady-state month. No numeric one-time implementation fee is asserted without scope and labour rates.', '',
      '## Cost controls before deployment', '',
      '1. Keep model calls explicitly requested; reuse current-context drafts and enforce tenant and platform quotas. Never silently retry an uncertain paid inference.',
      '2. Limit daily collection frequency and maintain incremental snapshots. Reuse billing exports where suitable rather than repeatedly querying historical ranges.',
      '3. Bound Athena scanned bytes by workgroup/query, use partitioned Parquet and materialize dashboard totals. Add byte/query limits for customer-side BigQuery.',
      '4. Keep DynamoDB access key-based, cap scans, monitor consumed units and indexes, and use S3 for large payloads.',
      '5. Measure actual tokens, Lambda duration, billed database units, data retention, scans and egress in staging. Recalculate before production approval.',
      '6. Set per-client budgets, anomaly alerts, queue/concurrency limits and an operator AI kill switch. Billing alerts alone are not a hard spending cap.', '',
      '## Workbook and verification', '',
      'Open the accompanying editable workbook and change the numeric scenario selector on Inputs and Rates: 1 Pilot, 2 Growth or 3 Scale. Blue cells are editable. One active calculation feeds Monthly Cost; Sources maps rate references to public URLs. Editing usage, rates, tax or FX recalculates the selected scenario.', '',
      'The three scenarios were reconciled to independent Decimal calculations. A zero-production-AI boundary was checked and no formula errors were found. The workbook was rendered for visual inspection. Native desktop Excel execution was not performed. The public price-list SKU/rate codes and retrieved dates are retained in the workbook and cost-model JSON. Refresh rates before purchase; actual AWS invoices may differ from this model.']
    Path('docs/SERVERLESS_COST_ESTIMATE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'FinOps_Autopilot_Cost_Estimate.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    ratebook=rates(); cases=[]
    for index,name in enumerate(['Pilot','Growth','Scale']):
        inputs={key:D(values[index]) for key,label,unit,values in DRIVERS}
        inputs.update(days=D(30),fx=D(90),tax=D('.18'),buffer=D('.25'))
        rows=[]
        for label,category,expression,rate_id,unit in LINES:
            quantity=evaluate(expression,inputs)
            rate=D(ratebook[rate_id]['value']) if rate_id else D(1)
            rows.append({'service':label,'category':category,'quantity':str(quantity),'rate':str(rate),'cost':str(quantity*rate)})
        subtotal=sum((D(row['cost']) for row in rows),D(0))
        ai=sum((D(row['cost']) for row in rows if row['category']=='AI'),D(0))
        nonprod=inputs['nonprod_allowance']
        # Three platform accounts: prod plus dev and staging. Bedrock is in the
        # support base. No temporary support/free-tier promotions are assumed.
        support_prod=max(D(29),min(subtotal,D(10000))*D('.09')+max(min(subtotal-D(10000),D(70000)),D(0))*D('.07')+max(min(subtotal-D(80000),D(170000)),D(0))*D('.05')+max(subtotal-D(250000),D(0))*D('.03'))
        support_nonprod=2*max(D(29),nonprod/2*D('.09'))
        pretax=subtotal+nonprod+support_prod+support_nonprod
        cash=pretax*(1+inputs['tax'])*inputs['fx']
        budget=cash*(1+inputs['buffer'])
        ce=inputs['customers']*inputs['aws_accounts']*inputs['days']*inputs['sync_daily']*inputs['ce_pages']*D(ratebook['ce_rate']['value'])
        totals={'production_services_usd':subtotal,'ai_usd':ai,'production_non_ai_usd':subtotal-ai,
            'nonproduction_usd':nonprod,'support_usd':support_prod+support_nonprod,'pretax_usd':pretax,
            'gst_assumption_usd':pretax*inputs['tax'],'monthly_inr_with_tax':cash,'budget_inr_with_25pct_buffer':budget,
            'annual_budget_inr':budget*12,'budget_per_customer_inr':budget/inputs['customers'],
            'customer_ce_usd':ce,'ai_calls':inputs['customers']*inputs['days']*inputs['ai_daily']}
        cases.append({'name':name,'inputs':{k:str(v) for k,v in inputs.items()},'lines':rows,'totals':{k:str(v) for k,v in totals.items()}})
    model={'as_of':DATE,'region':'ap-south-1','drivers':DRIVERS,'rates':ratebook,'line_definitions':LINES,'cases':cases,
        'globals':{'days':30,'fx':90,'tax':0.18,'buffer':0.25},
        'support_source':'https://aws.amazon.com/premiumsupport/pricing/'}
    (OUT/'cost-model.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    report(model)
    for case in cases:
        print(case['name'],json.dumps({k:str(D(v).quantize(D('.01'),rounding=ROUND_HALF_UP)) for k,v in case['totals'].items()}))


if __name__ == '__main__':
    main()
