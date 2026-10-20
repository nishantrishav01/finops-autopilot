import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from services.api.domain import assess, build_overview, money, total
from services.api.main import app
from services.api.store import database, get, items, put


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('FINOPS_DB', str(tmp_path / 'test.db'))
    monkeypatch.setenv('FINOPS_ENABLE_LIVE', 'false')
    from services.api.main import attempts
    attempts.clear()
    with TestClient(app) as c:
        yield c


def demo(c):
    from fastapi import Response
    from http.cookies import SimpleCookie
    from services.api.main import issue_session, password_hash
    from tests.seed_fixture import seed_tenant
    with database() as db:
        db.execute("INSERT OR IGNORE INTO tenants VALUES('tenant-demo','Northstar Technologies')")
        db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?)',
            ('user-demo','tenant-demo','demo@finops.local','Test Admin',password_hash('test-fixture-password'),'admin'))
        seed_tenant(db, 'tenant-demo')
        response = Response()
        issue_session(db, 'user-demo', response)
    cookie = SimpleCookie(response.headers['set-cookie'])
    c.cookies.set('finops_session', cookie['finops_session'].value)
    return c.get('/v1/recommendations').json()['items']


def signup(c, email='client@example.com'):
    r = c.post('/v1/auth/signup', json={'name': 'Client Admin', 'organization': 'Client One',
        'email': email, 'password': 'a-strong-local-password'})
    assert r.status_code == 201, r.text


def test_readiness_and_auth_required(client):
    assert client.get('/health').json()['status'] == 'ok'
    for path in ['/v1/connections', '/v1/overview', '/v1/audit', '/v1/reports']:
        r = client.get(path)
        assert r.status_code == 401
        assert r.json()['request_id']


def test_money_and_invalid_values():
    assert total(['0.10', '0.20']) == '0.30'
    assert money('1.005') == '1.01'
    assert money('-1.005') == '-1.01'
    assert total(['0.004', '0.004', '0.004']) == '0.01'
    assert money('12.5', 'JPY') == '13'
    assert money('0.1235', 'KWD') == '0.124'
    for value in ['NaN', 'Infinity', 'oops', '1000000000001', '1e-1000000']:
        with pytest.raises(ValueError):
            money(value)


def test_demo_provenance_and_currency(client):
    recs = demo(client)
    assert {r['provider'] for r in recs} == {'aws', 'azure', 'gcp'}
    assert all(r['evidence']['is_sample'] for r in recs)
    overview = client.get('/v1/overview').json()
    assert Decimal(overview['spend']) > 0
    assert overview['potential_basis'] == 'Synthetic scenario estimate'
    assert overview['realized'] is None
    assert len(overview['trend']) == 30
    assert client.get('/v1/overview?days=30').status_code == 200
    assert len(client.get('/v1/overview?days=7').json()['trend']) == 7
    assert client.get('/v1/overview?days=8').status_code == 422
    assert client.get('/v1/overview?currency=INR').json()['spend'] == '0.00'
    assert client.get('/v1/overview?currency=INR').json()['potential'] is None
    assert all(x['aws'] == '0.00' for x in client.get('/v1/overview?provider=gcp').json()['trend'])


def test_tenant_isolation_across_resources(client):
    recs = demo(client)
    job = client.post(f"/v1/recommendations/{recs[0]['id']}/analyze", json={'idempotency_key': 'tenant-test-key'}).json()
    report = client.post('/v1/reports').json()
    conn = client.get('/v1/connections').json()['items'][0]
    client.post('/v1/auth/logout')
    signup(client)
    assert client.get('/v1/connections').json()['items'] == []
    assert client.get('/v1/recommendations').json()['total'] == 0
    assert client.get('/v1/overview').json()['spend'] == '0.00'
    for path in [f"/v1/recommendations/{recs[0]['id']}", f"/v1/jobs/{job['id']}", f"/v1/reports/{report['id']}/download"]:
        assert client.get(path).status_code == 404
    assert client.post(f"/v1/connections/{conn['id']}/sync", json={'idempotency_key': 'isolation-key'}).status_code == 404


def test_job_idempotency_and_safe_policy(client):
    rec = next(r for r in demo(client) if r['evidence'].get('memory_peak') is None and r['category'] == 'compute')
    endpoint = f"/v1/recommendations/{rec['id']}/analyze"
    body = {'idempotency_key': 'same-analysis-key'}
    first, second = client.post(endpoint, json=body), client.post(endpoint, json=body)
    assert first.status_code == second.status_code == 202
    assert first.json()['id'] == second.json()['id']
    assert client.get(first.json()['status_url']).json()['status'] == 'SUCCEEDED'
    rec = client.get(f"/v1/recommendations/{rec['id']}").json()
    assert rec['analysis']['confidence'] is None
    assert rec['analysis']['model_status'] == 'NOT_CONFIGURED'
    assert rec['analysis']['choice'] == 'request_more_evidence'
    assert rec['status'] == 'NEEDS_REVIEW'
    r = client.post(f"/v1/recommendations/{rec['id']}/review", json={'version': rec['version'], 'decision': 'APPROVED_PLAN', 'justification': 'Verified by the owner.'})
    assert r.status_code == 409
    r = client.post(f"/v1/recommendations/{rec['id']}/review", json={'version': rec['version'], 'decision': 'DEFERRED', 'justification': 'Waiting for peak memory telemetry.'})
    assert r.status_code == 200
    assert r.json()['status'] == 'DEFERRED'


def test_approval_revision_and_no_cloud_execution(client):
    rec = next(r for r in demo(client) if r['provider'] == 'azure' and r['category'] == 'compute')
    client.post(f"/v1/recommendations/{rec['id']}/analyze", json={'idempotency_key': 'approve-test-key'})
    rec = client.get(f"/v1/recommendations/{rec['id']}").json()
    assert not rec['analysis']['gaps']
    payload = {'version': rec['version'], 'decision': 'APPROVED_PLAN', 'justification': 'Owner reviewed the sample change plan.'}
    result = client.post(f"/v1/recommendations/{rec['id']}/review", json=payload)
    assert result.status_code == 200
    assert result.json()['review']['evidence_hash']
    assert result.json()['status'] == 'APPROVED_PLAN'
    assert client.post(f"/v1/recommendations/{rec['id']}/review", json=payload).status_code == 409
    assert 'EXECUTED' not in str(client.get('/v1/audit').json())


def test_policy_rechecks_freshness_at_approval(client):
    rec = next(r for r in demo(client) if r['provider'] == 'azure' and r['category'] == 'compute')
    client.post(f"/v1/recommendations/{rec['id']}/analyze", json={'idempotency_key': 'freshness-test-key'})
    with database() as db:
        saved = get(db, 'tenant-demo', 'recommendation', rec['id'])
        saved['collected_at'] = (datetime.now(timezone.utc)-timedelta(hours=80)).isoformat()
        put(db, 'tenant-demo', 'recommendation', saved)
    result = client.post(f"/v1/recommendations/{rec['id']}/review", json={'version': saved['version'], 'decision': 'APPROVED_PLAN', 'justification': 'Attempt to approve stale evidence.'})
    assert result.status_code == 409


def test_signup_login_cookie_logout(client):
    signup(client)
    assert client.get('/v1/me').json()['organization'] == 'Client One'
    client.post('/v1/auth/logout')
    assert client.get('/v1/me').status_code == 401
    assert client.post('/v1/auth/login', json={'email': 'client@example.com', 'password': 'wrong'}).status_code == 401
    r = client.post('/v1/auth/login', json={'email': 'CLIENT@example.com', 'password': 'a-strong-local-password'})
    assert r.status_code == 200
    assert 'HttpOnly' in r.headers['set-cookie']
    assert 'SameSite=strict' in r.headers['set-cookie']


def test_origin_validation_and_secret_rejection(client):
    assert client.post('/v1/auth/demo', headers={'Origin': 'https://evil.example'}).status_code == 403
    demo(client)
    r = client.post('/v1/connections', json={'provider': 'aws', 'mode': 'live', 'name': 'Private AWS', 'account_id': '123456789010',
        'config': {'access_key': 'DO_NOT_ECHO_THIS'}})
    assert r.status_code == 422
    assert 'DO_NOT_ECHO_THIS' not in r.text


@pytest.mark.parametrize('provider,account,cfg', [
    ('aws', 'invalid', {}), ('azure', 'invalid', {}), ('gcp', 'UpperCase-Project', {}),
    ('aws', '123456789010', {'role_arn': 'arn:aws:iam::111111111111:role/WrongAccount'}),
    ('azure', '00000000-0000-4000-8000-000000000002', {'tenant_id': 'not-a-uuid'}),
    ('gcp', 'valid-project', {'billing_table': 'x`; SELECT *', 'billing_account_id': 'AAAAAA-BBBBBB-CCCCCC'}),
])
def test_invalid_cloud_scopes(client, provider, account, cfg):
    demo(client)
    assert client.post('/v1/connections', json={'provider': provider, 'mode': 'live', 'name': 'Test account', 'account_id': account, 'config': cfg}).status_code == 422


def test_live_off_retains_pending_and_generates_external_id(client):
    demo(client)
    data = {'provider': 'aws', 'mode': 'live', 'name': 'Client production', 'account_id': '123456789010',
        'config': {'role_arn': 'arn:aws:iam::123456789010:role/FinOpsReadOnly'}}
    c = client.post('/v1/connections', json=data).json()
    assert c['status'] == 'PENDING'
    assert len(c['config']['external_id']) >= 32
    assert client.post('/v1/connections', json=data).status_code == 409
    job = client.post(f"/v1/connections/{c['id']}/sync", json={'idempotency_key': 'disabled-live-sync'}).json()
    result = client.get(job['status_url']).json()
    assert result['status'] == 'FAILED'
    assert 'Live collection is disabled' in result['error']


def import_connection(client):
    return client.post('/v1/connections', json={'provider': 'azure', 'mode': 'import', 'name': 'Client CSV',
        'account_id': '00000000-0000-4000-8000-000000000002', 'config': {}}).json()


def test_billing_import_atomic_replace_and_currency(client):
    signup(client)
    c = import_connection(client)
    day = (datetime.now(timezone.utc)-timedelta(days=2)).date().isoformat()
    valid = f'date,service,amount,currency\n{day},Virtual Machines,0.10,USD\n{day},Storage,0.20,USD\n{day},Database,70.00,INR\n'
    endpoint = f"/v1/connections/{c['id']}/import"
    assert client.post(endpoint, json={'csv': valid}).json()['rows_imported'] == 3
    overview = client.get('/v1/overview').json()
    assert overview['spend'] == '0.30'
    assert overview['potential'] is None
    assert client.get('/v1/overview?currency=INR').json()['spend'] == '70.00'
    invalid = valid+f'{day},Broken,NaN,USD\n'
    assert client.post(endpoint, json={'csv': invalid}).status_code == 422
    assert client.get('/v1/overview').json()['spend'] == '0.30'
    # Idempotent snapshot replacement, not additive append.
    assert client.post(endpoint, json={'csv': valid}).status_code == 200
    assert client.get('/v1/overview').json()['spend'] == '0.30'
    assert client.post(endpoint, json={'csv': valid+f'{day},Storage,0.20,USD\n'}).status_code == 422


def test_source_recommendation_import_and_formula_export(client):
    signup(client)
    c = import_connection(client)
    body = {'title': '=HYPERLINK("http://example.com")', 'source_id': 'client-source', 'resource_id': 'vm-client', 'service': 'Virtual Machines',
        'category': 'compute', 'savings': '45.50', 'currency': 'USD', 'owner': 'Platform team', 'source': 'Customer source export',
        'observed_at': (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}
    endpoint = f"/v1/connections/{c['id']}/recommendations"
    assert client.post(endpoint, json=body).status_code == 201
    body['savings'] = '50.00'
    assert client.post(endpoint, json=body).status_code == 201
    assert client.get('/v1/recommendations').json()['total'] == 1
    assert client.get('/v1/overview').json()['potential'] is None
    report = client.post('/v1/reports').json()
    export = client.get(f"/v1/reports/{report['id']}/download")
    rows = list(csv.reader(io.StringIO(export.text.lstrip('\ufeff'))))
    assert rows[1][1].startswith("'=")
    assert rows[1][3] == '50.00'


def test_rbac_checks_server_membership(client):
    demo(client)
    with database() as db:
        db.execute("UPDATE users SET role='viewer' WHERE id='user-demo'")
    assert client.get('/v1/overview').status_code == 200
    assert client.put('/v1/policy', json={'max_evidence_age_hours': 24}).status_code == 403
    assert client.post('/v1/reports').status_code == 403


def test_persistence_across_sessions(client):
    signup(client)
    c = import_connection(client)
    client.post('/v1/auth/logout')
    client.post('/v1/auth/login', json={'email': 'client@example.com', 'password': 'a-strong-local-password'})
    assert client.get('/v1/connections').json()['items'][0]['id'] == c['id']


def test_superseded_recommendations_excluded_from_overview(client):
    recs = demo(client)
    with database() as db:
        rec = get(db, 'tenant-demo', 'recommendation', recs[0]['id'])
        rec['status'] = 'SUPERSEDED'
        put(db, 'tenant-demo', 'recommendation', rec)
    assert client.get('/v1/recommendations').json()['total'] == len(recs)-1
    assert client.get('/v1/overview').json()['opportunities'] == len(recs)-1
