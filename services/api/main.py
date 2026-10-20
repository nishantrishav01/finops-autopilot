import csv
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import advisor, connectors, vault
from .domain import assess, build_overview, cost_amount, evidence_hash, money
from .store import StoreConflict, audit, database, get, initialize, items, now, put, uid


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title='FinOps Autopilot', version='0.2.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['*'] if os.getenv('FINOPS_STORE') == 'dynamodb' else ['127.0.0.1', 'localhost', 'testserver'])
attempts = defaultdict(deque)


@app.exception_handler(StoreConflict)
async def store_conflict(request, exc):
    return JSONResponse({'code': 'WORKSPACE_CONFLICT', 'message': str(exc), 'request_id': request.state.request_id}, status_code=409)


@app.middleware('http')
async def request_context(request, call_next):
    request.state.request_id = uid('req')
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        parsed = urlparse(origin)
        cloud = os.getenv('FINOPS_STORE') == 'dynamodb'
        if cloud:
            from .cloud_auth import config
            trusted = origin == config()['origin']
        else:
            trusted = parsed.scheme == 'http' and parsed.netloc in (request.headers.get('host'), '127.0.0.1:5173', 'localhost:5173')
        if not trusted:
            return JSONResponse({'code': 'INVALID_ORIGIN', 'message': 'Untrusted browser origin.', 'request_id': request.state.request_id}, status_code=403)
    if request.url.path.startswith('/v1'):
        if int(request.headers.get('content-length', '0')) > 2_000_000:
            return JSONResponse({'code': 'PAYLOAD_TOO_LARGE', 'message': 'Request exceeds 2 MB.', 'request_id': request.state.request_id}, status_code=413)
        # Enforce the bound for chunked requests too, rather than trusting Content-Length.
        if request.method in ('POST', 'PUT', 'PATCH') and len(await request.body()) > 2_000_000:
            return JSONResponse({'code': 'PAYLOAD_TOO_LARGE', 'message': 'Request exceeds 2 MB.', 'request_id': request.state.request_id}, status_code=413)
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/v1'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'code': str(exc.status_code), 'message': exc.detail, 'request_id': request.state.request_id}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo a rejected request body; it may contain secrets in forbidden fields.
    details = [{'field': '.'.join(str(p) for p in e['loc']), 'message': e['msg']} for e in exc.errors()]
    return JSONResponse({'code': 'VALIDATION_ERROR', 'message': 'Please check the supplied fields.', 'details': details,
                         'request_id': request.state.request_id}, status_code=422)


@app.exception_handler(advisor.AdvisorError)
async def advisor_error(request, exc):
    return JSONResponse({'code': exc.code, 'message': str(exc), 'request_id': request.state.request_id}, status_code=exc.status)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Signup(Input):
    name: str = Field(min_length=2, max_length=80)
    organization: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12, max_length=256)


class Login(Input):
    email: str = Field(max_length=200)
    password: str = Field(max_length=256)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def auth_limit(request):
    key = request.client.host
    queue = attempts[key]
    while queue and queue[0] < time.time()-60:
        queue.popleft()
    if len(queue) >= 15:
        raise HTTPException(429, 'Too many sign-in attempts. Try again in a minute.')
    queue.append(time.time())


def issue_session(db, user, response):
    token = secrets.token_urlsafe(40)
    db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
    db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user, time.time()+8*3600))
    response.set_cookie('finops_session', token, httponly=True, samesite='strict', max_age=8*3600, path='/')


def user_session(request: Request):
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        from .cloud_auth import session_user
        return session_user(request)
    token = request.cookies.get('finops_session', '')
    with database() as db:
        row = db.execute('SELECT u.id,u.tenant_id,u.email,u.name,u.role,t.name AS organization FROM users u JOIN sessions s ON s.user_id=u.id JOIN tenants t ON t.id=u.tenant_id WHERE s.token_hash=? AND s.expires>?',
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if not row:
        raise HTTPException(401, 'Sign in to your workspace.')
    return dict(row)


def admin(user=Depends(user_session)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Tenant administrator permission required.')
    return user


def analyst(user=Depends(user_session)):
    if user['role'] not in ('admin', 'analyst'):
        raise HTTPException(403, 'Analyst permission required.')
    return user


def reviewer(user=Depends(user_session)):
    if user['role'] not in ('admin', 'reviewer', 'approver'):
        raise HTTPException(403, 'Reviewer permission required.')
    return user


def require(db, tenant, kind, identifier):
    value = get(db, tenant, kind, identifier)
    if value is None:
        raise HTTPException(404, 'Record not found in this workspace.')
    return value


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'serverless' if os.getenv('FINOPS_STORE') == 'dynamodb' else 'local', 'version': '0.2.0'}


@app.get('/v1/auth/config')
def auth_config():
    return {'mode': 'cognito' if os.getenv('FINOPS_STORE') == 'dynamodb' else 'local'}


@app.get('/v1/auth/start')
def cloud_login():
    if os.getenv('FINOPS_STORE') != 'dynamodb':
        raise HTTPException(404, 'Cognito is available on the cloud deployment.')
    from .cloud_auth import start
    return start()


@app.get('/v1/auth/callback')
def cloud_callback(request: Request):
    if os.getenv('FINOPS_STORE') != 'dynamodb':
        raise HTTPException(404, 'Cognito is available on the cloud deployment.')
    from .cloud_auth import callback
    return callback(request)


@app.post('/v1/auth/signup', status_code=201)
def signup(body: Signup, response: Response, request: Request):
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        raise HTTPException(403, 'Use Cognito to create your account.')
    auth_limit(request)
    tenant, user = uid('tenant'), uid('user')
    try:
        with database() as db:
            db.execute('INSERT INTO tenants VALUES(?,?)', (tenant, body.organization))
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?)', (user, tenant, body.email.lower(), body.name, password_hash(body.password), 'admin'))
            audit(db, tenant, body.email.lower(), 'WORKSPACE_CREATED', body.organization)
            issue_session(db, user, response)
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'An account with that email already exists.') from None
    return {'id': user}


@app.post('/v1/auth/login')
def login(body: Login, response: Response, request: Request):
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        raise HTTPException(403, 'Use Cognito to sign in.')
    auth_limit(request)
    with database() as db:
        row = db.execute('SELECT * FROM users WHERE email=?', (body.email.lower(),)).fetchone()
        expected = row['password'] if row else password_hash('dummy-unmatched-password')
        actual = password_hash(body.password, expected.split(':')[0])
        if not row or not secrets.compare_digest(expected, actual):
            raise HTTPException(401, 'Email or password is incorrect.')
        issue_session(db, row['id'], response)
        audit(db, row['tenant_id'], row['email'], 'SIGNED_IN', row['id'])
    return {'ok': True}


@app.post('/v1/auth/logout')
def logout(request: Request, response: Response):
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        from .cloud_auth import logout as cloud_logout
        return cloud_logout(request, response)
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(request.cookies.get('finops_session', '').encode()).hexdigest(),))
    response.delete_cookie('finops_session')
    return {'ok': True}


@app.get('/v1/me')
def me(user=Depends(user_session)):
    return {**user, 'deployment': 'serverless' if os.getenv('FINOPS_STORE') == 'dynamodb' else 'local', 'live_enabled': os.getenv('FINOPS_ENABLE_LIVE', 'false').lower() == 'true'}


class ConnectionCreate(Input):
    provider: Literal['aws', 'azure', 'gcp']
    mode: Literal['live', 'import']
    name: str = Field(min_length=2, max_length=80)
    account_id: str = Field(min_length=3, max_length=100)
    config: dict[str, str] = Field(default_factory=dict)

    @field_validator('config')
    @classmethod
    def no_secrets(cls, value):
        if set(value) - {'auth_method', 'role_arn', 'region', 'tenant_id', 'billing_table', 'billing_account_id', 'query_project'}:
            raise ValueError('Unsupported configuration field. Configure credentials outside the application.')
        if any(len(v) > 250 for v in value.values()):
            raise ValueError('Configuration value exceeds length limit.')
        return value


def validate_connection(body):
    if body.provider == 'aws' and not re.fullmatch(r'\d{12}', body.account_id):
        raise HTTPException(422, 'AWS account ID must contain 12 digits.')
    if body.provider == 'azure' and not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', body.account_id):
        raise HTTPException(422, 'Enter a valid Azure subscription UUID.')
    if body.provider == 'gcp' and not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', body.account_id):
        raise HTTPException(422, 'Enter a valid GCP project ID (6–30 lowercase characters).')
    if body.mode != 'live':
        return
    cfg = body.config
    if body.provider == 'aws':
        method = cfg.get('auth_method', 'role')
        if method not in ('role', 'access_key'):
            raise HTTPException(422, 'Select role or access_key authentication.')
        if method == 'role' and not re.fullmatch(r'arn:aws:iam::'+body.account_id+r':role/[\w+=,.@/-]+', cfg.get('role_arn', '')):
            raise HTTPException(422, 'Read-only role ARN must belong to the supplied AWS account (commercial partition).')
        if os.getenv('FINOPS_STORE') == 'dynamodb' and method == 'role' and not re.fullmatch(r'arn:aws:iam::'+body.account_id+r':role/FinOpsAutopilotReadOnly[\w+=,.@-]*', cfg.get('role_arn', '')):
            raise HTTPException(422, 'Cloud collector roles must be named FinOpsAutopilotReadOnly with an optional suffix.')
        if cfg.get('region') and not re.fullmatch(r'[a-z]{2}-[a-z]+-\d', cfg['region']):
            raise HTTPException(422, 'Invalid AWS region identifier.')
    if body.provider == 'azure' and not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', cfg.get('tenant_id', '')):
        raise HTTPException(422, 'Enter the Azure directory tenant UUID.')
    if body.provider == 'gcp':
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+', cfg.get('billing_table', '')):
            raise HTTPException(422, 'Enter the GCP billing export table as project.dataset.table.')
        if not re.fullmatch(r'[A-Fa-f0-9]{6}-[A-Fa-f0-9]{6}-[A-Fa-f0-9]{6}', cfg.get('billing_account_id', '')):
            raise HTTPException(422, 'Enter the billing account ID in XXXXXX-XXXXXX-XXXXXX format.')


@app.get('/v1/connections')
def connections(user=Depends(user_session)):
    with database() as db:
        return {'items': items(db, user['tenant_id'], 'connection')}


@app.post('/v1/connections', status_code=201)
def create_connection(body: ConnectionCreate, user=Depends(admin)):
    validate_connection(body)
    tenant = user['tenant_id']
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if any(c['provider'] == body.provider and c['account_id'] == body.account_id and c['mode'] == body.mode for c in items(db, tenant, 'connection')):
            raise HTTPException(409, 'This cloud scope is already registered in this mode.')
        c = {'id': uid('con'), **body.model_dump(), 'status': 'PENDING', 'created_at': now(), 'last_sync': None,
             'potential': None, 'currency': 'USD', 'error': None, 'coverage': 'Not collected'}
        if body.provider == 'aws' and body.mode == 'live':
            c['config'].setdefault('auth_method', 'role')
            c['config'].setdefault('region', 'ap-south-1')
            if c['config']['auth_method'] == 'role':
                c['config']['external_id'] = 'finops-'+secrets.token_urlsafe(32)
                if os.getenv('FINOPS_COLLECTOR_PRINCIPAL'):
                    c['config']['collector_principal'] = os.environ['FINOPS_COLLECTOR_PRINCIPAL']
            else:
                c['credentials_configured'] = False
        put(db, tenant, 'connection', c)
        audit(db, tenant, user['email'], 'CONNECTION_CREATED', c['id'], f"{body.provider} / {body.mode}; read-only")
    return c


class AWSCredentials(Input):
    access_key_id: SecretStr
    secret_access_key: SecretStr
    session_token: SecretStr = SecretStr('')


@app.put('/v1/connections/{identifier}/credentials')
def save_credentials(identifier: str, body: AWSCredentials, user=Depends(admin)):
    values = {key: value.get_secret_value() for key, value in body}
    if not re.fullmatch(r'(?:AKIA|ASIA)[A-Z0-9]{16}', values['access_key_id']) or not re.fullmatch(r'[A-Za-z0-9/+=]{40}', values['secret_access_key']):
        raise HTTPException(422, 'Enter a valid AWS access key ID and 40-character secret key.')
    if len(values['session_token']) > 10000 or (values['access_key_id'].startswith('ASIA') and not values['session_token']):
        raise HTTPException(422, 'Temporary AWS keys require a session token (maximum 10,000 characters).')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        c = require(db, user['tenant_id'], 'connection', identifier)
        if c['provider'] != 'aws' or c['mode'] != 'live' or c['config'].get('auth_method') != 'access_key':
            raise HTTPException(409, 'This connection does not use AWS access keys.')
        if any(j['target'] == identifier and j['status'] in ('QUEUED', 'RUNNING') for j in items(db, user['tenant_id'], 'job')):
            raise HTTPException(409, 'Wait for the current collection before rotating credentials.')
        try:
            version = vault.save(user['tenant_id'], identifier, values)
        except Exception:
            raise HTTPException(503, 'Credentials could not be securely stored. Check the runtime vault configuration.') from None
        c.update(credentials_configured=True, credential_version=version, status='PENDING', error=None)
        put(db, user['tenant_id'], 'connection', c)
        audit(db, user['tenant_id'], user['email'], 'AWS_CREDENTIALS_UPDATED', identifier, 'Write-only credential storage; verification required.')
    return {'configured': True, 'verification': 'pending'}


class JobRequest(Input):
    idempotency_key: str = Field(min_length=8, max_length=100)


def enqueue(db, user, kind, target, key):
    tenant = user['tenant_id']
    existing = next((x for x in items(db, tenant, 'job') if x['key'] == key), None)
    if existing:
        if existing['kind'] != kind or existing['target'] != target:
            raise HTTPException(409, 'Idempotency key was used for another operation.')
        return existing, False
    if any(x['status'] in ('QUEUED', 'RUNNING') and x['target'] == target for x in items(db, tenant, 'job')):
        raise HTTPException(409, 'An operation for this resource is already running.')
    if len([x for x in items(db, tenant, 'job') if x['created_at'][:10] == now()[:10]]) >= 100:
        raise HTTPException(429, 'Local workspace daily job quota reached (100).')
    job = {'id': uid('job'), 'kind': kind, 'target': target, 'key': key, 'status': 'QUEUED', 'created_at': now(),
           'actor': user['email'], 'error': None}
    put(db, tenant, 'job', job)
    audit(db, tenant, user['email'], kind.upper()+'_QUEUED', target)
    return job, True


def run_job(tenant, jobid):
    with database() as db:
        job = require(db, tenant, 'job', jobid)
        job['status'] = 'RUNNING'
        put(db, tenant, 'job', job)
        target = require(db, tenant, 'connection' if job['kind'] == 'sync' else 'recommendation', job['target'])
    result = None
    try:
        if job['kind'] == 'sync' and target['mode'] == 'live':
            result = connectors.collect(target, tenant=tenant)
            if os.getenv('FINOPS_STORE') == 'dynamodb' and len(result['recommendations']) > 40:
                result['recommendations'] = sorted(result['recommendations'], key=lambda r: Decimal(r['savings']), reverse=True)[:40]
                result['warnings'].append('This deployment retains the top 40 source recommendations per account. The provider-deduplicated account savings summary covers the full source scope; individual retained estimates must not be summed.')
        elif job['kind'] == 'advisor':
            if job.get('source_version') != target['version']:
                raise advisor.AdvisorError('ADVICE_CONTEXT_CHANGED', 'Source revision changed before the Bedrock job started. Reload and request a new draft.')
            result = advisor.generate(tenant, job, target)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            if job['kind'] == 'sync':
                if target['mode'] == 'import':
                    raise connectors.ConnectorError('This is an import connection. Upload a new CSV to refresh it.')
                else:
                    save_collection(db, tenant, target, result)
                job['status'] = 'PARTIAL' if result and result['warnings'] else 'SUCCEEDED'
                job['warnings'] = result['warnings'] if result else []
            elif job['kind'] == 'advisor':
                rec = require(db, tenant, 'recommendation', target['id'])
                advisor.commit_result(db, tenant, rec, result)
                job.update(status='SUCCEEDED', result_url=f"/v1/recommendations/{rec['id']}/advice", cache_hit=result['cache_hit'])
                audit(db, tenant, job['actor'], 'BEDROCK_ADVICE_ACCEPTED', rec['id'],
                    f"{result['model_id']}; prompt={result['prompt_version']}; generation={result['generation_id']}; cache={result['cache_hit']}")
            else:
                rec = require(db, tenant, 'recommendation', target['id'])
                if rec['version'] != target['version']:
                    raise connectors.ConnectorError('Evidence changed during analysis. Retry against the latest version.')
                policy = get(db, tenant, 'policy', 'default') or {}
                rec.update(analysis=assess(rec, policy), status='NEEDS_REVIEW', version=rec['version']+1)
                rec['analysis']['at'] = now()
                put(db, tenant, 'recommendation', rec)
                job['status'] = 'SUCCEEDED'
            job['ended_at'] = now()
            put(db, tenant, 'job', job)
            audit(db, tenant, job['actor'], job['kind'].upper()+'_COMPLETED', target['id'], job['status'])
    except Exception as exc:
        # Provider errors can contain bearer tokens or customer metadata. Persist only an allowlisted message.
        message = str(exc) if isinstance(exc, (connectors.ConnectorError, advisor.AdvisorError)) else 'Provider request failed. Check local credential setup, scope permissions and billing availability; see docs/CONNECTORS.md.'
        if job['kind'] == 'advisor' and result and not result.get('cache_hit'):
            advisor.finish_usage(tenant, jobid, 'DISCARDED')
        with database() as db:
            job.update(status='FAILED', error=message, ended_at=now())
            if isinstance(exc, advisor.AdvisorError):
                job['error_code'] = exc.code
            put(db, tenant, 'job', job)
            if job['kind'] == 'sync':
                c = require(db, tenant, 'connection', target['id'])
                c.update(status='ERROR', error=message)
                put(db, tenant, 'connection', c)
            audit(db, tenant, job['actor'], job['kind'].upper()+'_FAILED', target['id'], message)


def save_collection(db, tenant, connection, result):
    timestamp = now()
    snapshotid = uid('snapshot')
    raw = result['raw']
    put(db, tenant, 'snapshot', {'id': snapshotid, 'connection_id': connection['id'], 'at': timestamp,
        'source': result['source'], 'hash': evidence_hash(raw), 'raw': json.loads(json.dumps(raw, default=str))})
    normalized = [{**cost, 'id': f"{connection['id']}:{i}", 'connection_id': connection['id'],
        'provider': connection['provider'], 'source': result['source'], 'snapshot_id': snapshotid, 'collected_at': timestamp} for i, cost in enumerate(result['costs'])]
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        from .cloud_store import blob_write
        key = f"curated/tenant={tenant}/connection={connection['id']}/snapshot={snapshotid}/billing.jsonl"
        blob_write(key, normalized, jsonl=True)
        put(db, tenant, 'billing', {'id': connection['id'], 'key': key, 'snapshot_id': snapshotid, 'rows': len(normalized)})
    else:
        for old in items(db, tenant, 'cost'):
            if old['connection_id'] == connection['id']:
                db.execute('DELETE FROM entities WHERE tenant_id=? AND kind=? AND id=?', (tenant, 'cost', old['id']))
        for cost in normalized:
            put(db, tenant, 'cost', cost)
    # Archive all superseded source recommendations, so vanished opportunities cannot be approved.
    for old in items(db, tenant, 'recommendation'):
        if old['connection_id'] == connection['id'] and old.get('source_kind') != 'manual-import':
            old.update(status='SUPERSEDED', version=old['version']+1, analysis=None)
            put(db, tenant, 'recommendation', old)
    for rec in result['recommendations']:
        rid = connection['id']+':'+rec['source_id']
        old = get(db, tenant, 'recommendation', rid)
        put(db, tenant, 'recommendation', {**rec, 'id': rid, 'connection_id': connection['id'],
            'provider': connection['provider'], 'risk': 'High', 'environment': 'Unknown', 'owner': None,
            'status': 'NEW', 'mode': 'live', 'version': old['version']+1 if old else 1, 'collected_at': timestamp,
            'snapshot_id': snapshotid, 'analysis': None})
    connection.update(status='PARTIAL' if result['warnings'] else 'CONNECTED', last_sync=timestamp,
        potential=result['potential'], currency=result['currency'], coverage='Billing collected', warnings=result['warnings'], error=None)
    put(db, tenant, 'connection', connection)


@app.post('/v1/connections/{identifier}/sync', status_code=202)
def sync(identifier: str, body: JobRequest, tasks: BackgroundTasks, user=Depends(analyst)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require(db, user['tenant_id'], 'connection', identifier)
        job, fresh = enqueue(db, user, 'sync', identifier, body.idempotency_key)
    if fresh and os.getenv('FINOPS_STORE') != 'dynamodb':
        tasks.add_task(run_job, user['tenant_id'], job['id'])
    return {**job, 'status_url': '/v1/jobs/'+job['id']}


@app.get('/v1/jobs/{identifier}')
def job(identifier: str, user=Depends(user_session)):
    with database() as db:
        return require(db, user['tenant_id'], 'job', identifier)


@app.get('/v1/overview')
def overview(days: int = Query(30, ge=7, le=90), provider: Literal['all', 'aws', 'azure', 'gcp'] = 'all',
             currency: str = Query('USD', pattern=r'^[A-Z]{3}$'), mode: Literal['all', 'live', 'import'] = 'all', user=Depends(user_session)):
    if days not in (7, 30, 90):
        raise HTTPException(422, 'Date range must be 7, 30 or 90 days.')
    with database() as db:
        tenant = user['tenant_id']
        return build_overview(items(db, tenant, 'connection'), items(db, tenant, 'cost'),
            items(db, tenant, 'recommendation'), days, provider, currency, mode)


@app.get('/v1/recommendations')
def recommendations(provider: str = 'all', risk: str = 'all', status: str = 'all', q: str = Query('', max_length=100),
                    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user=Depends(user_session)):
    with database() as db:
        rows = [r for r in items(db, user['tenant_id'], 'recommendation') if r['status'] != 'SUPERSEDED' and
            (provider == 'all' or r['provider'] == provider) and (risk == 'all' or r['risk'] == risk) and
            (status == 'all' or r['status'] == status) and q.lower() in (r['title']+' '+r['resource_id']+' '+r['service']).lower()]
        rows.sort(key=lambda r: Decimal(r['savings']), reverse=True)
        return {'items': rows[offset:offset+limit], 'total': len(rows), 'next_offset': offset+limit if offset+limit < len(rows) else None}


@app.get('/v1/recommendations/{identifier}')
def recommendation(identifier: str, user=Depends(user_session)):
    with database() as db:
        rec = require(db, user['tenant_id'], 'recommendation', identifier)
        return {**rec, 'advisory': advisor.guidance_record(db, user['tenant_id'], rec)}


@app.get('/v1/ai/status')
def ai_status(user=Depends(user_session)):
    with database() as db:
        return advisor.state(db, user['tenant_id'])


@app.put('/v1/ai/governance')
def ai_governance(body: advisor.Governance, user=Depends(admin)):
    cfg = advisor.runtime_config()
    if body.enabled and (not body.data_processing_approved or body.runtime_fingerprint != cfg['fingerprint']):
        raise HTTPException(409, 'Review the current model, region and transfer notice and explicitly approve processing before enabling AI.')
    if body.enabled and cfg['global_target'] and body.residency_mode != 'global_approved':
        raise HTTPException(409, 'The selected Opus global route cannot meet India-only processing. Leave AI disabled or explicitly approve global processing for this client.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = advisor.governance(db, user['tenant_id'])
        if previous['version'] != body.version:
            raise HTTPException(409, 'Workspace AI policy changed. Reload before saving.')
        saved = {'id': 'default', **body.model_dump(), 'version': previous['version']+1,
            'approved_at': now() if body.data_processing_approved else None,
            'approved_by': user['email'] if body.data_processing_approved else None}
        put(db, user['tenant_id'], 'ai_policy', saved)
        audit(db, user['tenant_id'], user['email'], 'AI_GOVERNANCE_UPDATED', 'default',
            f"enabled={body.enabled}; approved={body.data_processing_approved}; residency={body.residency_mode}; providers={','.join(body.allowed_providers)}; version={saved['version']}; runtime={body.runtime_fingerprint}; transfer={advisor.TRANSFER_VERSION}")
        return advisor.state(db, user['tenant_id'])


class AdvisorRequest(JobRequest):
    version: int = Field(ge=1)
    objective: Literal['reduce_waste', 'balance_performance', 'understand_risk'] = 'balance_performance'


@app.post('/v1/recommendations/{identifier}/advise', status_code=202)
def advise(identifier: str, body: AdvisorRequest, tasks: BackgroundTasks, user=Depends(analyst)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        rec = require(db, user['tenant_id'], 'recommendation', identifier)
        if rec['version'] != body.version or rec['status'] == 'SUPERSEDED':
            raise HTTPException(409, 'The source recommendation changed. Reload before requesting Bedrock guidance.')
        if not rec.get('analysis'):
            raise HTTPException(409, 'Assess the evidence before requesting Bedrock guidance.')
        advisor.check_access(advisor.governance(db, user['tenant_id']), advisor.runtime_config(), rec)
        job, fresh = enqueue(db, user, 'advisor', identifier, body.idempotency_key)
        if not fresh and job.get('objective') != body.objective:
            raise HTTPException(409, 'Idempotency key was used for a different guidance objective.')
        if fresh:
            job['objective'] = body.objective
            job['source_version'] = body.version
            put(db, user['tenant_id'], 'job', job)
    if fresh and os.getenv('FINOPS_STORE') != 'dynamodb':
        tasks.add_task(run_job, user['tenant_id'], job['id'])
    return {**job, 'status_url': '/v1/jobs/'+job['id']}


@app.get('/v1/recommendations/{identifier}/advice')
def advice(identifier: str, user=Depends(user_session)):
    with database() as db:
        rec = require(db, user['tenant_id'], 'recommendation', identifier)
        result = advisor.guidance_record(db, user['tenant_id'], rec)
        if not result:
            raise HTTPException(404, 'No validated Bedrock guidance has been generated for this opportunity.')
        return result


class AdviceFeedback(Input):
    generation_id: str = Field(min_length=5, max_length=100)
    verdict: Literal['helpful', 'inaccurate', 'unsafe']


@app.post('/v1/recommendations/{identifier}/advice/feedback')
def advice_feedback(identifier: str, body: AdviceFeedback, user=Depends(analyst)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require(db, user['tenant_id'], 'recommendation', identifier)
        saved = require(db, user['tenant_id'], 'advice', identifier)
        if saved['generation_id'] != body.generation_id:
            raise HTTPException(409, 'This AI draft changed. Review the current generation before leaving feedback.')
        feedback = {'id': body.generation_id+':'+user['id'], **body.model_dump(), 'recommendation_id': identifier,
            'actor': user['email'], 'at': now()}
        put(db, user['tenant_id'], 'ai_feedback', feedback)
        audit(db, user['tenant_id'], user['email'], 'AI_FEEDBACK_RECORDED', identifier, body.verdict)
    return {'ok': True}


@app.post('/v1/recommendations/{identifier}/analyze', status_code=202)
def analyze(identifier: str, body: JobRequest, tasks: BackgroundTasks, user=Depends(analyst)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        rec = require(db, user['tenant_id'], 'recommendation', identifier)
        if rec['status'] == 'SUPERSEDED':
            raise HTTPException(409, 'Source recommendation was superseded. Refresh the list.')
        job, fresh = enqueue(db, user, 'analysis', identifier, body.idempotency_key)
    if fresh and os.getenv('FINOPS_STORE') != 'dynamodb':
        tasks.add_task(run_job, user['tenant_id'], job['id'])
    return {**job, 'status_url': '/v1/jobs/'+job['id']}


class Review(Input):
    version: int = Field(ge=1)
    decision: Literal['APPROVED_PLAN', 'REJECTED', 'DEFERRED']
    justification: str = Field(min_length=10, max_length=2000)


@app.post('/v1/recommendations/{identifier}/review')
def review(identifier: str, body: Review, user=Depends(reviewer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        rec = require(db, user['tenant_id'], 'recommendation', identifier)
        if rec['version'] != body.version:
            raise HTTPException(409, 'This recommendation changed. Reload before reviewing.')
        if rec['status'] != 'NEEDS_REVIEW' or not rec.get('analysis'):
            raise HTTPException(409, 'Run an evidence assessment before reviewing this plan.')
        if body.decision == 'APPROVED_PLAN':
            current = assess(rec, get(db, user['tenant_id'], 'policy', 'default') or {})
            if current['gaps']:
                raise HTTPException(409, 'Evidence policy blocks approval. Resolve the gaps or defer this plan.')
        rec.update(status=body.decision, version=rec['version']+1,
            review={'actor': user['email'], 'at': now(), 'justification': body.justification,
                    'evidence_hash': evidence_hash(rec['evidence']), 'policy_version': 'deterministic-policy-v1', 'source_version': body.version})
        put(db, user['tenant_id'], 'recommendation', rec)
        audit(db, user['tenant_id'], user['email'], body.decision, identifier, body.justification)
    return rec


class BillingImport(Input):
    csv: str = Field(min_length=1, max_length=1_800_000)


@app.post('/v1/connections/{identifier}/import')
def import_billing(identifier: str, body: BillingImport, user=Depends(analyst)):
    reader = csv.DictReader(io.StringIO(body.csv.lstrip('\ufeff')))
    if set(reader.fieldnames or []) != {'date', 'service', 'amount', 'currency'}:
        raise HTTPException(422, 'CSV columns must be date,service,amount,currency.')
    costs, keys = [], set()
    try:
        for row in reader:
            if len(costs) >= 10000:
                raise ValueError('Maximum 10,000 rows per import.')
            day = date.fromisoformat(row['date'])
            if day >= date.today():
                raise ValueError('Billing dates must precede today; only completed days are accepted.')
            if not row['service'].strip() or len(row['service']) > 150 or not re.fullmatch('[A-Z]{3}', row['currency']):
                raise ValueError('Each row needs a service and a three-letter currency.')
            key = (row['date'], row['service'], row['currency'])
            if key in keys:
                raise ValueError('Duplicate date/service/currency. Aggregate line items before importing.')
            keys.add(key)
            costs.append({**row, 'amount': cost_amount(row['amount'])})
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, f'Invalid billing CSV near row {len(costs)+2}: {exc}') from None
    if not costs:
        raise HTTPException(422, 'CSV has no billing rows.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        c = require(db, user['tenant_id'], 'connection', identifier)
        if c['mode'] != 'import':
            raise HTTPException(409, 'Create an Import connection to upload billing data.')
        save_collection(db, user['tenant_id'], c, {'costs': costs, 'recommendations': [], 'potential': None,
            'currency': costs[0]['currency'], 'raw': {'csv': body.csv}, 'warnings': [], 'source': 'Customer CSV import; unverified source'})
        audit(db, user['tenant_id'], user['email'], 'BILLING_IMPORTED', identifier, f'{len(costs)} rows; replaced prior snapshot')
    return {'rows_imported': len(costs)}


class RecommendationImport(Input):
    title: str = Field(min_length=5, max_length=160)
    source_id: str = Field(min_length=1, max_length=200)
    resource_id: str = Field(min_length=2, max_length=300)
    service: str = Field(min_length=2, max_length=100)
    category: Literal['compute', 'storage', 'commitment', 'anomaly']
    savings: str = Field(max_length=30)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    owner: str = Field(min_length=2, max_length=100)
    environment: Literal['Production', 'Development', 'Staging', 'Unknown'] = 'Unknown'
    region: str = Field(default='unknown', max_length=80)
    source: str = Field(min_length=3, max_length=200)
    observed_at: datetime


@app.post('/v1/connections/{identifier}/recommendations', status_code=201)
def import_rec(identifier: str, body: RecommendationImport, user=Depends(analyst)):
    try:
        amount = money(body.savings, body.currency)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if Decimal(amount) < 0 or body.observed_at.tzinfo is None or body.observed_at > datetime.now(timezone.utc):
        raise HTTPException(422, 'Use a nonnegative estimate and a past source timestamp with timezone.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        c = require(db, user['tenant_id'], 'connection', identifier)
        rid = c['id']+':import:'+hashlib.sha256(body.source_id.encode()).hexdigest()[:24]
        old = get(db, user['tenant_id'], 'recommendation', rid)
        rec = {**body.model_dump(mode='json'), 'id': rid, 'connection_id': c['id'], 'provider': c['provider'],
            'mode': c['mode'], 'savings': amount, 'risk': 'High', 'status': 'NEW', 'analysis': None,
            'source_kind': 'manual-import', 'version': old['version']+1 if old else 1, 'collected_at': body.observed_at.isoformat(),
            'evidence': {'source': body.source, 'source_id': body.source_id, 'is_sample': False,
                'cpu_peak': None, 'memory_peak': None, 'rollback_verified': False,
                'limitations': ['Customer-provided estimate. Source and telemetry require independent verification.']}}
        put(db, user['tenant_id'], 'recommendation', rec)
        audit(db, user['tenant_id'], user['email'], 'RECOMMENDATION_IMPORTED', rid)
    return rec


@app.get('/v1/audit')
def audit_events(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user=Depends(user_session)):
    with database() as db:
        events = sorted(items(db, user['tenant_id'], 'audit'), key=lambda e: e['at'], reverse=True)
        return {'items': events[offset:offset+limit], 'total': len(events)}


@app.get('/v1/policy')
def policy(user=Depends(user_session)):
    with database() as db:
        return get(db, user['tenant_id'], 'policy', 'default') or {'id': 'default', 'max_evidence_age_hours': 48}


class Policy(Input):
    max_evidence_age_hours: int = Field(ge=1, le=168)


@app.put('/v1/policy')
def update_policy(body: Policy, user=Depends(admin)):
    with database() as db:
        result = put(db, user['tenant_id'], 'policy', {'id': 'default', **body.model_dump()})
        audit(db, user['tenant_id'], user['email'], 'POLICY_UPDATED', 'default', f'Evidence max age: {body.max_evidence_age_hours} hours')
    return result


def safe_cell(value):
    value = str(value)
    return "'"+value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


@app.get('/v1/reports')
def reports(user=Depends(user_session)):
    with database() as db:
        rows = sorted(items(db, user['tenant_id'], 'report'), key=lambda x: x['at'], reverse=True)
        return {'items': [{k: v for k, v in row.items() if k != 'csv'} for row in rows]}


@app.post('/v1/reports', status_code=201)
def create_report(user=Depends(analyst)):
    with database() as db:
        rows = items(db, user['tenant_id'], 'recommendation')
        text = io.StringIO(newline='')
        writer = csv.writer(text)
        writer.writerow(['provider', 'title', 'resource', 'monthly_estimate', 'currency', 'risk', 'status', 'source', 'collected_at', 'data_mode', 'version'])
        for r in rows:
            if r['status'] != 'SUPERSEDED':
                writer.writerow([safe_cell(v) for v in [r['provider'], r['title'], r['resource_id'], r['savings'], r['currency'],
                    r['risk'], r['status'], r['evidence']['source'], r['collected_at'], r['mode'], r['version']]])
        report = {'id': uid('report'), 'at': now(), 'name': 'Optimization opportunities', 'format': 'CSV',
                  'rows': len([r for r in rows if r['status'] != 'SUPERSEDED']), 'csv': text.getvalue()}
        put(db, user['tenant_id'], 'report', report)
        audit(db, user['tenant_id'], user['email'], 'REPORT_CREATED', report['id'], 'Potential estimates; not realized savings. Individual estimates may overlap.')
    return {k: v for k, v in report.items() if k != 'csv'}


@app.get('/v1/reports/{identifier}/download')
def download(identifier: str, user=Depends(user_session)):
    with database() as db:
        report = require(db, user['tenant_id'], 'report', identifier)
        audit(db, user['tenant_id'], user['email'], 'REPORT_DOWNLOADED', identifier)
    if 'csv_key' in report:
        from .cloud_store import blob_read
        report['csv'] = blob_read(report['csv_key'])
    return Response('\ufeff'+report['csv'], media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="finops-{identifier}.csv"'})


# A built frontend can be served by the same loopback API process.
web_dist = Path(__file__).resolve().parents[2] / 'apps' / 'web' / 'dist'
if web_dist.exists():
    app.mount('/', StaticFiles(directory=web_dist, html=True), name='web')
