"""Cognito authorization-code + PKCE login; tokens never reach browser JavaScript.

Runtime config is an SSM JSON document populated by CDK after CloudFront/Cognito
creation, avoiding CloudFormation dependency cycles. It contains no secrets.
"""
import base64
import hashlib
import json
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from .store import audit, database, get, put, uid


@lru_cache(maxsize=1)
def config():
    import os
    from .cloud_store import client
    return json.loads(client('ssm').get_parameter(Name=os.environ['FINOPS_AUTH_CONFIG'])['Parameter']['Value'])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session_user(request):
    token = request.cookies.get('finops_session', '')
    with database() as db:
        session = get(db, '_sessions', 'session', digest(token)) if token else None
        user = get(db, '_identity', 'membership', session['user_id']) if session and session['expires'] > time.time() else None
    if not user or user.get('disabled'):
        raise HTTPException(401, 'Sign in to your workspace.')
    return user


def start():
    cfg = config()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    with database() as db:
        put(db, '_oauth', 'state', {'id': digest(state), 'verifier': verifier, 'expires': int(time.time()+300), 'used': False})
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    query = urlencode({'response_type': 'code', 'client_id': cfg['client_id'], 'redirect_uri': cfg['origin']+'/v1/auth/callback',
        'scope': 'openid email profile aws.cognito.signin.user.admin', 'state': state, 'code_challenge_method': 'S256', 'code_challenge': challenge})
    response = RedirectResponse(cfg['domain']+'/oauth2/authorize?'+query, status_code=302)
    response.set_cookie('finops_oauth_state', state, max_age=300, secure=True, httponly=True, samesite='lax', path='/v1/auth')
    return response


def callback(request: Request):
    cfg = config()
    state, code = request.query_params.get('state', ''), request.query_params.get('code', '')
    cookie = request.cookies.get('finops_oauth_state', '')
    if not state or not code or not cookie or not secrets.compare_digest(state, cookie):
        raise HTTPException(400, 'Login state did not match. Start sign-in again.')
    with database() as db:
        saved = get(db, '_oauth', 'state', digest(state))
        if not saved or saved['used'] or saved['expires'] < time.time():
            raise HTTPException(400, 'Login expired or was already used. Start sign-in again.')
        saved['used'] = True
        put(db, '_oauth', 'state', saved)
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as transport:
            response = transport.post(cfg['domain']+'/oauth2/token', data={'grant_type': 'authorization_code',
                'client_id': cfg['client_id'], 'redirect_uri': cfg['origin']+'/v1/auth/callback', 'code': code, 'code_verifier': saved['verifier']})
            response.raise_for_status()
            access_token = response.json()['access_token']
        from .cloud_store import client
        identity = client('cognito-idp').get_user(AccessToken=access_token)
        attributes = {a['Name']: a['Value'] for a in identity['UserAttributes']}
        if attributes.get('email_verified') != 'true':
            raise ValueError('Unverified identity')
        identifier = attributes['sub']
    except Exception:
        raise HTTPException(401, 'Cognito sign-in could not be verified. Start again.') from None
    with database() as db:
        user = get(db, '_identity', 'membership', identifier)
        if not user:
            tenant = uid('tenant')
            name = attributes.get('name') or attributes['email'].split('@')[0]
            user = {'id': identifier, 'tenant_id': tenant, 'email': attributes['email'], 'name': name,
                'organization': name+"'s workspace", 'role': 'admin'}
            put(db, '_identity', 'membership', user)
            audit(db, tenant, user['email'], 'WORKSPACE_CREATED', tenant)
        if user.get('disabled'):
            raise HTTPException(403, 'Workspace membership is disabled.')
        token = secrets.token_urlsafe(40)
        put(db, '_sessions', 'session', {'id': digest(token), 'user_id': identifier, 'expires': int(time.time()+3600)})
        audit(db, user['tenant_id'], user['email'], 'SIGNED_IN', identifier)
    response = RedirectResponse(cfg['origin']+'/', status_code=302)
    response.set_cookie('finops_session', token, max_age=3600, httponly=True, secure=True, samesite='strict', path='/')
    response.delete_cookie('finops_oauth_state', path='/v1/auth')
    return response


def logout(request, response):
    with database() as db:
        identifier = digest(request.cookies.get('finops_session', ''))
        db.delete('_sessions', 'session', identifier)
    response.delete_cookie('finops_session', path='/', secure=True, httponly=True, samesite='strict')
    return {'ok': True}
