"""Provider contract tests. Never contact a real cloud account."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.api import connectors


def test_aws_scope_tokens_and_authoritative_savings(monkeypatch):
    boto3 = pytest.importorskip('boto3')
    from botocore.stub import Stubber
    session = boto3.Session(aws_access_key_id='testing', aws_secret_access_key='testing', region_name='us-east-1')
    sts, ce, hub = [session.client(s) for s in ['sts', 'ce', 'cost-optimization-hub']]
    end = date.today()
    conn = {'provider': 'aws', 'account_id': '123456789012', 'config': {
        'role_arn': 'arn:aws:iam::123456789012:role/FinOpsReadOnly', 'external_id': 'unique-external-id'}}
    with Stubber(sts) as st, Stubber(ce) as cost, Stubber(hub) as coh:
        st.add_response('assume_role', {'Credentials': {'AccessKeyId': 'ASIA'+'A'*16, 'SecretAccessKey': 'a'*40,
            'SessionToken': 'temporary-test-token', 'Expiration': datetime.now(timezone.utc)+timedelta(minutes=15)}},
            {'RoleArn': conn['config']['role_arn'], 'ExternalId': 'unique-external-id', 'RoleSessionName': 'finops-readonly', 'DurationSeconds': 900})
        st.add_response('get_caller_identity', {'Account': '123456789012', 'Arn': 'arn:aws:sts::123456789012:assumed-role/FinOpsReadOnly/test', 'UserId': 'TEST'})
        params = {'TimePeriod': {'Start': (end-timedelta(days=90)).isoformat(), 'End': end.isoformat()},
            'Granularity': 'DAILY', 'Metrics': ['AmortizedCost'], 'Filter': {'And': [
                {'Dimensions': {'Key': 'LINKED_ACCOUNT', 'Values': ['123456789012']}},
                {'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Credit', 'Refund']}}}]},
            'GroupBy': [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]}
        def period(amount):
            return {'TimePeriod': {'Start': (end-timedelta(days=2)).isoformat(), 'End': (end-timedelta(days=1)).isoformat()},
                'Groups': [{'Keys': ['Amazon EC2'], 'Metrics': {'AmortizedCost': {'Amount': amount, 'Unit': 'USD'}}}]}
        cost.add_response('get_cost_and_usage', {'ResultsByTime': [period('12.10')], 'NextPageToken': 'page2'}, params)
        cost.add_response('get_cost_and_usage', {'ResultsByTime': [period('1.25')]}, {**params, 'NextPageToken': 'page2'})
        coh.add_response('list_recommendation_summaries', {'estimatedTotalDedupedSavings': 42.5, 'currencyCode': 'USD',
            'items': [{'group': '123456789012', 'estimatedMonthlySavings': 999.0}]},
            {'groupBy': 'AccountId', 'filter': {'accountIds': ['123456789012']}})
        coh.add_response('list_recommendations', {'items': [{'recommendationId': 'source-id', 'accountId': '123456789012',
            'currentResourceType': 'Ec2Instance', 'actionType': 'Rightsize', 'estimatedMonthlySavings': 999.0,
            'lastRefreshTimestamp': datetime.now(timezone.utc)-timedelta(days=2), 'recommendationLookbackPeriodInDays': 14,
            'currencyCode': 'USD', 'resourceId': 'i-test'}]},
            {'filter': {'accountIds': ['123456789012']}, 'includeAllRecommendations': False})
        monkeypatch.setattr(boto3, 'Session', lambda **kw: SimpleNamespace(client=lambda name, **opts: {'sts': sts, 'ce': ce, 'cost-optimization-hub': hub}[name]))
        result = connectors.aws_collect(conn)
        assert [r['amount'] for r in result['costs']] == ['12.10', '1.25']
        assert result['potential'] == '42.50'
        assert result['recommendations'][0]['savings'] == '999.00'
        assert result['recommendations'][0]['source_updated_at']
        assert result['recommendations'][0]['evidence']['memory_peak'] is None
        st.assert_no_pending_responses(); cost.assert_no_pending_responses(); coh.assert_no_pending_responses()


def test_azure_subscription_scope_and_continuation(monkeypatch):
    identity = pytest.importorskip('azure.identity')
    credential = MagicMock()
    credential.get_token.return_value.token = 'not-a-real-token'
    monkeypatch.setattr(identity, 'DefaultAzureCredential', lambda **kw: credential)
    account, tenant = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
    calls = []
    def arm(url, token, payload=None):
        calls.append((url, payload))
        if len(calls) == 1:
            return {'subscriptionId': account, 'tenantId': tenant}
        cols = [{'name': n} for n in ['PreTaxCost', 'ServiceName', 'UsageDate', 'Currency']]
        return {'properties': {'columns': cols, 'rows': [[Decimal('12.10'), 'Virtual Machines', 20261015, 'USD']],
            'nextLink': f'https://management.azure.com/subscriptions/{account}/providers/Microsoft.CostManagement/query?page=2' if len(calls) == 2 else None}}
    monkeypatch.setattr(connectors, 'arm_json', arm)
    result = connectors.azure_collect({'account_id': account, 'config': {'tenant_id': tenant}})
    assert len(result['costs']) == 2
    assert result['costs'][0]['date'] == '2026-10-15'
    assert result['potential'] is None
    assert result['warnings']
    assert calls[1][1]['type'] == 'ActualCost'
    assert calls[1][1] == calls[2][1]
    credential.close.assert_called_once()


def test_azure_rejects_wrong_directory(monkeypatch):
    identity = pytest.importorskip('azure.identity')
    monkeypatch.setattr(identity, 'DefaultAzureCredential', lambda **kw: MagicMock())
    monkeypatch.setattr(connectors, 'arm_json', lambda *args: {'subscriptionId': 'sub', 'tenantId': 'wrong'})
    with pytest.raises(connectors.ConnectorError, match='does not match'):
        connectors.azure_collect({'account_id': 'sub', 'config': {'tenant_id': 'requested'}})


def test_gcp_parameters_credits_and_scan_cap(monkeypatch):
    bigquery = pytest.importorskip('google.cloud.bigquery')
    client = MagicMock()
    client.query.return_value.job_id = 'test-job'
    client.query.return_value.result.return_value = [SimpleNamespace(day=date(2026, 10, 15), service='BigQuery', currency='USD', amount=Decimal('0.30'))]
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: client)
    result = connectors.gcp_collect({'account_id': 'client-project', 'config': {'billing_table': 'billing-project.dataset.export',
        'billing_account_id': 'AAAAAA-BBBBBB-CCCCCC', 'query_project': 'query-project'}})
    assert result['costs'][0]['amount'] == '0.30'
    args, kwargs = client.query.call_args
    assert 'UNNEST(credits)' in args[0]
    assert 'project.id = @project AND billing_account_id = @billing' in args[0]
    cfg = kwargs['job_config']
    assert cfg.maximum_bytes_billed == 1024**3
    assert {p.name: p.value for p in cfg.query_parameters}['project'] == 'client-project'
    client.close.assert_called_once()


def test_gcp_empty_scope_not_verified(monkeypatch):
    bigquery = pytest.importorskip('google.cloud.bigquery')
    client = MagicMock()
    client.query.return_value.result.return_value = []
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: client)
    with pytest.raises(connectors.ConnectorError, match='No billing export rows'):
        connectors.gcp_collect({'account_id': 'client-project', 'config': {'billing_table': 'billing-project.dataset.export', 'billing_account_id': 'AAAAAA-BBBBBB-CCCCCC'}})
