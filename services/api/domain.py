"""Canonical amounts and deterministic policy. No model output authorizes a change."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

CENT = Decimal('0.01')


def cost_amount(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal('1000000000000'):
            raise ValueError('Amount must be finite and within supported bounds.')
        if amount.as_tuple().exponent < -18:
            raise ValueError('Amounts support at most 18 fractional digits.')
        return format(amount, 'f')
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid monetary amount.') from None


def money(value, currency='USD'):
    zero = {'BIF','CLP','DJF','GNF','ISK','JPY','KMF','KRW','PYG','RWF','UGX','UYI','VND','VUV','XAF','XOF','XPF'}
    three = {'BHD','IQD','JOD','KWD','LYD','OMR','TND'}
    places = 0 if currency in zero else 3 if currency in three else 4 if currency in {'CLF','UYW'} else 2
    # Calculated Decimal ratios may have more than 18 fractional places. Bound
    # external input first; round internal arithmetic only at the summary edge.
    amount = value if isinstance(value, Decimal) else Decimal(cost_amount(value))
    try:
        rounded = amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('Invalid monetary amount.') from None
    return cost_amount(rounded)


def total(values, currency='USD'):
    return money(sum((Decimal(str(v)) for v in values), Decimal(0)), currency)


def evidence_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def assess(rec, policy):
    gaps = []
    evidence = rec['evidence']
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(rec.get('source_updated_at') or rec['collected_at'])).total_seconds() / 3600
    if rec.get('mode') == 'live' and rec.get('source_kind') != 'manual-import' and not rec.get('source_updated_at'):
        gaps.append('Provider recommendation freshness timestamp is unavailable.')
    if age > policy.get('max_evidence_age_hours', 48):
        gaps.append('Evidence is stale. Refresh the source before approval.')
    if not rec.get('owner'):
        gaps.append('Assign an accountable workload owner.')
    if rec['category'] == 'compute':
        if evidence.get('cpu_peak') is None:
            gaps.append('Peak CPU telemetry is missing.')
        elif evidence['cpu_peak'] > 80:
            gaps.append('Peak CPU exceeds the 80% review threshold.')
        if evidence.get('memory_peak') is None:
            gaps.append('Peak memory telemetry is missing.')
    if evidence.get('rollback_verified') is not True:
        gaps.append('A workload owner must verify the rollback plan.')
    if rec.get('environment') == 'Production' and not evidence.get('maintenance_window'):
        gaps.append('A production maintenance window is required.')
    if rec['category'] == 'commitment':
        gaps.append('Commitment utilization, overlap and financial approval require manual verification.')
    if rec['category'] == 'storage' and not evidence.get('dependencies_verified'):
        gaps.append('Verify resource dependencies and backup coverage.')
    route = {'compute': 'investigate_rightsizing', 'storage': 'investigate_storage',
             'commitment': 'investigate_commitments', 'anomaly': 'investigate_anomaly'}.get(rec['category'], 'request_more_evidence')
    return {'engine': 'deterministic-policy-v1', 'model_status': 'NOT_CONFIGURED',
            'model_id': None, 'confidence': None, 'choice': 'request_more_evidence' if gaps else route,
            'suggested_route': route, 'outcome': 'NEEDS_EVIDENCE' if gaps else 'REVIEWABLE_PLAN',
            'gaps': gaps, 'evidence_hash': evidence_hash(evidence),
            'summary': f"{rec['title']} has a source estimate of {rec['currency']} {rec['savings']}/month. " +
                       ('Approval is blocked until the evidence gaps below are resolved.' if gaps else 'Evidence meets the local review policy. An authorized reviewer may approve the plan.'),
            'change_plan': ['Confirm the owner, source estimate and workload requirements.',
                            'Validate the candidate in a non-production environment.',
                            'Implement through the customer change process in the approved window.',
                            'Compare post-change workload SLOs and normalized billing.'],
            'rollback_plan': 'The workload owner must retain the current configuration and verify restoration steps before implementation.'}


def build_overview(connections, costs, recs, days, provider, currency, mode):
    today = date.today()
    end = today
    start = end - timedelta(days=days)
    previous = start - timedelta(days=days)
    selected = [c for c in connections if (provider == 'all' or c['provider'] == provider)
                and (mode == 'all' or c['mode'] == mode)]
    ids = {c['id'] for c in selected}
    scoped = [x for x in costs if x['connection_id'] in ids and x['currency'] == currency]
    current = [x for x in scoped if start.isoformat() <= x['date'] < end.isoformat()]
    prior = [x for x in scoped if previous.isoformat() <= x['date'] < start.isoformat()]
    spend, old = total((x['amount'] for x in current), currency), total((x['amount'] for x in prior), currency)
    grouped = [{'provider': p, 'amount': total((x['amount'] for x in current if x['provider'] == p), currency),
                'accounts': len([c for c in selected if c['provider'] == p])} for p in ['aws', 'azure', 'gcp']]
    trend = []
    for i in range(days):
        day = start + timedelta(days=i)
        row = {'date': day.isoformat()}
        for p in ['aws', 'azure', 'gcp']:
            row[p] = total((x['amount'] for x in current if x['date'] == day.isoformat() and x['provider'] == p), currency)
        trend.append(row)
    available = [c for c in selected if c.get('potential') is not None and c.get('currency') == currency]
    potential = total((c['potential'] for c in available), currency) if available else None
    eligible = [r for r in recs if r['connection_id'] in ids and r['currency'] == currency and r['status'] not in ('REJECTED', 'DEFERRED', 'SUPERSEDED')]
    return {'spend': spend, 'previous_spend': old,
            'change_percent': money((Decimal(spend) - Decimal(old)) / Decimal(old) * 100) if Decimal(old) else None,
            'potential': potential, 'potential_coverage': f'{len(available)}/{len(selected)}',
            'potential_basis': 'Synthetic scenario estimate' if available and all(c['mode'] == 'demo' for c in available) else 'Provider-deduplicated AWS estimate; other providers excluded',
            'realized': None, 'currency': currency, 'start': start.isoformat(), 'end_exclusive': end.isoformat(),
            'trend': trend, 'by_provider': grouped, 'accounts': len(selected),
            'opportunities': len(eligible), 'review_count': len([r for r in eligible if r['status'] == 'NEEDS_REVIEW']),
            'fresh_accounts': len([c for c in selected if c['status'] in ('CONNECTED', 'DEMO', 'PARTIAL') and c.get('last_sync') and
                (datetime.now(timezone.utc) - datetime.fromisoformat(c['last_sync'])).total_seconds() <= 48 * 3600]),
            'recommendations': sorted(eligible, key=lambda r: Decimal(r['savings']), reverse=True)[:5],
            'currencies': sorted({x['currency'] for x in costs if x['connection_id'] in ids} | {'USD'}),
            'mixed_data': len({c['mode'] for c in selected}) > 1,
            'cost_basis': 'AWS amortized; Azure actual pre-tax; GCP net after credits. Not a reconciled invoice.',
            'stale_accounts': [c['name'] for c in selected if not c.get('last_sync') or
                (datetime.now(timezone.utc) - datetime.fromisoformat(c['last_sync'])).total_seconds() > 48 * 3600]}
