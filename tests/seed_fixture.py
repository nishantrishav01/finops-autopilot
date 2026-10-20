"""Explicitly synthetic, repeatable sample data; never used by a live collector."""
from datetime import date, timedelta
from decimal import Decimal
from services.api.store import put, items, now, audit
from services.api.domain import money, evidence_hash

SAMPLES = [
    ('aws', 'Production · AWS', '123456789012', ['EC2', 'RDS', 'S3', 'CloudWatch'], 1534),
    ('azure', 'Platform · Azure', '00000000-0000-4000-8000-000000000001', ['Virtual Machines', 'SQL Database', 'Storage', 'Networking'], 835),
    ('gcp', 'Analytics · GCP', 'sample-analytics', ['Compute Engine', 'BigQuery', 'Cloud Storage', 'Cloud SQL'], 586),
]


def seed_connection(db, tenant, connection):
    p = connection['provider']
    config = next(s for s in SAMPLES if s[0] == p)
    identifier = connection['id']
    timestamp = now()
    # Overwrite this connection's scenario snapshot rather than append costs on every refresh.
    for old in items(db, tenant, 'cost'):
        if old['connection_id'] == identifier:
            db.execute('DELETE FROM entities WHERE tenant_id=? AND kind=? AND id=?', (tenant, 'cost', old['id']))
    for i in range(90):
        day = date.today() - timedelta(days=90-i)
        factor = Decimal(100 + ((i * 17 + len(p)) % 23) - (8 if i > 59 else 0)) / 100
        for j, service in enumerate(config[3]):
            amount = money(Decimal(config[4]) * factor * [Decimal('.52'), Decimal('.25'), Decimal('.15'), Decimal('.08')][j])
            put(db, tenant, 'cost', {'id': f'{identifier}:{day}:{j}', 'connection_id': identifier,
                'provider': p, 'date': day.isoformat(), 'service': service, 'amount': amount, 'currency': 'USD',
                'source': 'synthetic-fixture', 'collected_at': timestamp})
    samples = {
        'aws': [('Rightsize underutilized EC2 instances', 'EC2', 'compute', '4200.00', 'Medium', 'Production', 'checkout-api', None),
                ('Review unattached EBS volumes', 'EBS', 'storage', '860.00', 'Low', 'Development', 'dev-storage', 38),
                ('Optimize database instance capacity', 'RDS', 'compute', '1280.00', 'High', 'Production', 'orders-db', None)],
        'azure': [('Resize development virtual machines', 'Virtual Machines', 'compute', '2160.00', 'Low', 'Development', 'platform-dev', 44),
                  ('Review idle managed disks', 'Managed Disks', 'storage', '480.00', 'Low', 'Development', 'build-cache', 20)],
        'gcp': [('Right-size analytics worker pool', 'Compute Engine', 'compute', '1640.00', 'Medium', 'Production', 'analytics-workers', 58),
                ('Review committed use discounts', 'Compute Engine', 'commitment', '1180.00', 'High', 'Production', 'analytics-commitment', None)],
    }
    values = samples[p]
    for i, (title, service, category, savings, risk, env, resource, memory) in enumerate(values):
        recid = f'{identifier}:rec:{i}'
        old = next((x for x in items(db, tenant, 'recommendation') if x['id'] == recid), None)
        # Refresh changes the evidence generation; previous approvals cannot carry forward.
        evidence = {'source': {'aws': 'Cost Optimization Hub', 'azure': 'Azure Advisor', 'gcp': 'Google Cloud Recommender'}[p] + ' · sample',
            'source_id': f'sample-{p}-{i}', 'cpu_average': 14 + i * 3, 'cpu_peak': 48 + i * 4,
            'memory_peak': memory, 'rollback_verified': memory is not None,
            'dependencies_verified': memory is not None, 'maintenance_window': 'Sunday 02:00–04:00 UTC' if memory else None,
            'observation_start': (date.today()-timedelta(days=30)).isoformat(), 'observation_end_exclusive': date.today().isoformat(),
            'is_sample': True, 'limitations': ['Synthetic evidence for local workflow evaluation. Not a client recommendation.']}
        put(db, tenant, 'recommendation', {'id': recid, 'connection_id': identifier, 'provider': p,
            'title': title, 'service': service, 'category': category, 'savings': savings, 'currency': 'USD',
            'risk': risk, 'environment': env, 'resource_id': resource, 'region': {'aws': 'us-east-1', 'azure': 'eastus', 'gcp': 'us-central1'}[p],
            'owner': 'Platform team' if p != 'gcp' else 'Data engineering', 'status': 'NEW', 'mode': 'demo',
            'version': old['version']+1 if old else 1, 'collected_at': timestamp, 'evidence': evidence, 'analysis': None})
    connection.update(status='DEMO', last_sync=timestamp, potential=money(sum(Decimal(r[3]) for r in values)), currency='USD',
                      coverage='Synthetic scenario', error=None)
    put(db, tenant, 'connection', connection)
    snapshot = {'id': f'{identifier}:{timestamp}', 'connection_id': identifier, 'at': timestamp,
                'source': 'synthetic-fixture', 'records': len(values), 'evidence_hash': evidence_hash(values)}
    put(db, tenant, 'snapshot', snapshot)


def seed_tenant(db, tenant):
    if items(db, tenant, 'connection'):
        return
    for p, name, account, _, _ in SAMPLES:
        seed_connection(db, tenant, {'id': f'demo-{p}', 'name': name, 'provider': p, 'account_id': account,
            'mode': 'demo', 'status': 'DEMO', 'config': {}, 'created_at': now(), 'last_sync': None, 'potential': None})
    put(db, tenant, 'policy', {'id': 'default', 'max_evidence_age_hours': 48})
    audit(db, tenant, 'Local system', 'WORKSPACE_CREATED', 'Northstar Technologies', 'Synthetic multi-cloud sample data loaded.')
