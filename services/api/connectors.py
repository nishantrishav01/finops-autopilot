"""Read-only billing collectors. Secrets are resolved only at runtime."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import re
import urllib.request
from .domain import cost_amount, money


class ConnectorError(Exception):
    pass


def collect(connection, tenant=None):
    if os.getenv('FINOPS_ENABLE_LIVE', 'false').lower() != 'true':
        raise ConnectorError('Live collection is disabled. Set FINOPS_ENABLE_LIVE=true after configuring read-only local credentials; see docs/CONNECTORS.md.')
    try:
        if connection['provider'] == 'aws' and connection['config'].get('auth_method') == 'access_key':
            from . import vault
            if not tenant:
                raise ConnectorError('Credential scope is missing.')
            return aws_collect(connection, vault.load(tenant, connection['id'], connection.get('credential_version')))
        return {'aws': aws_collect, 'azure': azure_collect, 'gcp': gcp_collect}[connection['provider']](connection)
    except ImportError:
        raise ConnectorError('Cloud SDK is not installed. Install requirements-cloud.txt and retry.') from None


def aws_collect(connection, credentials=None):
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    from botocore.paginate import Paginator
    cfg = connection['config']
    client_config = Config(retries={'mode': 'adaptive', 'total_max_attempts': 3}, connect_timeout=5, read_timeout=30)
    if cfg.get('auth_method', 'role') == 'access_key':
        if not credentials:
            raise ConnectorError('Save credentials before collecting this account.')
        creds = {'AccessKeyId': credentials['access_key_id'], 'SecretAccessKey': credentials['secret_access_key'],
                 'SessionToken': credentials.get('session_token') or None}
    else:
        session = boto3.Session(region_name=cfg.get('region', 'ap-south-1'))
        assumed = session.client('sts', config=client_config).assume_role(RoleArn=cfg['role_arn'],
            ExternalId=cfg['external_id'], RoleSessionName='finops-readonly', DurationSeconds=900)
        creds = assumed['Credentials']
    scoped = boto3.Session(aws_access_key_id=creds['AccessKeyId'], aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'], region_name=cfg.get('region', 'us-east-1'))
    identity = scoped.client('sts', config=client_config).get_caller_identity()
    if identity['Account'] != connection['account_id']:
        raise ConnectorError('Authenticated AWS identity does not match the configured AWS account.')
    # Runtime date, end-exclusive. Never query a fabricated historical current date.
    end = date.today()
    start = end - timedelta(days=90)
    ce = scoped.client('ce', region_name='us-east-1', config=client_config)
    costs, raw = [], []
    # Cost Explorer exposes NextPageToken but does not ship a paginator model.
    # Use the SDK pagination engine with the API's documented token contract.
    paginator = Paginator(ce.get_cost_and_usage,
        {'input_token': 'NextPageToken', 'output_token': 'NextPageToken', 'result_key': 'ResultsByTime'},
        ce.meta.service_model.operation_model('GetCostAndUsage'))
    for page in paginator.paginate(
        TimePeriod={'Start': start.isoformat(), 'End': end.isoformat()}, Granularity='DAILY', Metrics=['AmortizedCost'],
        Filter={'And': [{'Dimensions': {'Key': 'LINKED_ACCOUNT', 'Values': [connection['account_id']]}},
                        {'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Credit', 'Refund']}}}]},
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]):
        raw.append(page)
        for period in page.get('ResultsByTime', []):
            for group in period.get('Groups', []):
                m = group['Metrics']['AmortizedCost']
                costs.append({'date': period['TimePeriod']['Start'], 'service': group['Keys'][0],
                    'amount': cost_amount(m['Amount']), 'currency': m['Unit']})
    hub = scoped.client('cost-optimization-hub', region_name='us-east-1', config=client_config)
    recs, potential, currency, warnings = [], None, 'USD', []
    try:
        summary = hub.list_recommendation_summaries(groupBy='AccountId', filter={'accountIds': [connection['account_id']]})
        raw.append({'coh_summary': summary})
        potential = money(summary['estimatedTotalDedupedSavings']) if summary.get('estimatedTotalDedupedSavings') is not None else None
        currency = summary.get('currencyCode', 'USD')
        for page in hub.get_paginator('list_recommendations').paginate(filter={'accountIds': [connection['account_id']]}, includeAllRecommendations=False):
            raw.append({'coh_recommendations': page})
            for r in page.get('items', []):
                if r.get('accountId') != connection['account_id']:
                    continue
                action = r.get('actionType', 'Review')
                category = 'commitment' if 'Purchase' in action else 'storage' if 'Volume' in r.get('currentResourceType', '') else 'compute'
                refreshed = r.get('lastRefreshTimestamp')
                source_at = refreshed.isoformat() if refreshed else None
                source_date = refreshed.date() if refreshed else None
                lookback = r.get('recommendationLookbackPeriodInDays')
                recs.append({'source_id': r['recommendationId'], 'title': f"{action} · {r.get('currentResourceType', 'Resource')}",
                    'source_updated_at': source_at,
                    'resource_id': r.get('resourceArn', r.get('resourceId', 'Unknown')), 'service': r.get('currentResourceType', 'AWS'),
                    'category': category, 'savings': money(r.get('estimatedMonthlySavings', 0)), 'currency': r.get('currencyCode', currency),
                    'region': r.get('region', 'global'), 'evidence': {'source': 'AWS Cost Optimization Hub', 'source_id': r['recommendationId'],
                    'source_updated_at': source_at,
                    'observation_start': (source_date-timedelta(days=lookback)).isoformat() if source_date and lookback else None,
                    'observation_end_exclusive': source_date.isoformat() if source_date else None,
                    'cpu_peak': None, 'memory_peak': None, 'rollback_verified': False, 'is_sample': False,
                    'limitations': ['COH source estimate only. Detailed telemetry and owner validation have not been collected.',
                                    'Observation dates are derived from source refresh/lookback metadata; actual telemetry coverage requires detailed collection.']}})
    except ClientError:
        warnings.append('Cost Optimization Hub unavailable. Verify enrollment and read permissions. Billing collected; savings coverage is unavailable.')
    return {'costs': costs, 'recommendations': recs, 'potential': potential, 'currency': currency, 'raw': raw,
            'warnings': warnings, 'source': 'AWS Cost Explorer / Cost Optimization Hub'}


def arm_json(url, token, payload=None):
    # Continuation URLs must remain on the provider endpoint and subscription path.
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'management.azure.com':
        raise ConnectorError('Invalid Azure API continuation endpoint.')
    request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, method='POST' if payload is not None else 'GET')
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response, parse_float=Decimal)


def azure_collect(connection):
    from azure.identity import DefaultAzureCredential
    scope = f"/subscriptions/{connection['account_id']}"
    cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    try:
        token = cred.get_token('https://management.azure.com/.default').token
        identity = arm_json(f'https://management.azure.com{scope}?api-version=2022-12-01', token)
        if identity['subscriptionId'].lower() != connection['account_id'].lower() or identity.get('tenantId', '').lower() != connection['config']['tenant_id'].lower():
            raise ConnectorError('Azure subscription or directory does not match the requested scope.')
        end = date.today()
        payload = {'type': 'ActualCost', 'timeframe': 'Custom', 'timePeriod': {
            'from': (end-timedelta(days=90)).isoformat()+'T00:00:00Z', 'to': (end-timedelta(days=1)).isoformat()+'T23:59:59Z'},
            'dataset': {'granularity': 'Daily', 'aggregation': {'totalCost': {'name': 'PreTaxCost', 'function': 'Sum'}},
                        'grouping': [{'type': 'Dimension', 'name': 'ServiceName'}]}}
        url = f'https://management.azure.com{scope}/providers/Microsoft.CostManagement/query?api-version=2025-03-01'
        costs, raw, seen = [], [], set()
        while url:
            if url in seen or len(seen) >= 100 or not url.startswith(f'https://management.azure.com{scope}/'):
                raise ConnectorError('Azure pagination exceeded its safety boundary.')
            seen.add(url)
            page = arm_json(url, token, payload)
            raw.append(page)
            props = page.get('properties', {})
            columns = [c['name'] for c in props.get('columns', [])]
            for values in props.get('rows', []):
                row = dict(zip(columns, values))
                day = str(row['UsageDate'])
                costs.append({'date': f'{day[:4]}-{day[4:6]}-{day[6:8]}', 'service': row['ServiceName'],
                    'amount': cost_amount(row.get('PreTaxCost', row.get('Cost'))), 'currency': row['Currency']})
            url = props.get('nextLink')
        return {'costs': costs, 'recommendations': [], 'potential': None, 'currency': costs[0]['currency'] if costs else 'USD',
            'raw': raw, 'warnings': ['Billing only. Azure Advisor recommendation collection is not implemented; source estimates can be imported separately.'],
            'source': 'Azure Cost Management'}
    finally:
        cred.close()


def gcp_collect(connection):
    from google.cloud import bigquery
    cfg = connection['config']
    table = cfg['billing_table']
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+', table):
        raise ConnectorError('Use a project.dataset.table billing export identifier.')
    end = date.today()
    client = bigquery.Client(project=cfg.get('query_project') or connection['account_id'])
    try:
        # Parameterize customer scope; only the tightly validated table identifier is interpolated.
        query = f'''SELECT DATE(usage_start_time, 'UTC') AS day, service.description AS service, currency,
          SUM(CAST(cost AS NUMERIC) + IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC)) FROM UNNEST(credits) c), 0)) AS amount
          FROM `{table}` WHERE usage_start_time >= TIMESTAMP(@start) AND usage_start_time < TIMESTAMP(@end)
          AND project.id = @project AND billing_account_id = @billing GROUP BY day,service,currency'''
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=1024**3, use_query_cache=True,
            query_parameters=[bigquery.ScalarQueryParameter('start', 'DATE', end-timedelta(days=90)),
                bigquery.ScalarQueryParameter('end', 'DATE', end),
                bigquery.ScalarQueryParameter('project', 'STRING', connection['account_id']),
                bigquery.ScalarQueryParameter('billing', 'STRING', cfg['billing_account_id'])])
        job = client.query(query, job_config=job_config, timeout=30)
        costs = [{'date': r.day.isoformat(), 'service': r.service, 'currency': r.currency, 'amount': cost_amount(r.amount)}
                 for r in job.result(timeout=90)]
        if not costs:
            raise ConnectorError('No billing export rows match this project and billing account in the last 90 days. Verify scope and export freshness.')
        return {'costs': costs, 'recommendations': [], 'potential': None, 'currency': costs[0]['currency'],
            'raw': {'query_job_id': job.job_id, 'rows': costs},
            'warnings': ['Billing only. Google Cloud Recommender collection is not implemented; source estimates can be imported separately.'],
            'source': 'Google Cloud Billing export / BigQuery'}
    finally:
        client.close()
