import json
import os
from pathlib import Path
import pytest
from tests.test_application import client, signup
from services.api import vault


def key_input():
    return {'access_key_id':'AKIA'+'A'*16,'secret_access_key':'b'*40,'session_token':''}


def register(client):
    signup(client)
    result=client.post('/v1/connections',json={'provider':'aws','mode':'live','name':'Customer AWS','account_id':'123456789010','config':{'auth_method':'access_key'}})
    assert result.status_code==201
    return result.json()['id']


def test_demo_endpoints_and_source_modes_are_removed(client):
    assert client.post('/v1/auth/demo').status_code in (404,405)
    signup(client)
    assert client.post('/v1/connections',json={'provider':'aws','mode':'demo','name':'removed','account_id':'123456789010'}).status_code==422
    assert client.get('/v1/overview').json()['accounts']==0


@pytest.mark.skipif(os.name!='nt',reason='DPAPI is Windows-only')
def test_write_only_credentials_never_leak_to_api_or_database(client,tmp_path,monkeypatch):
    directory=tmp_path/'vault'
    monkeypatch.setenv('FINOPS_VAULT_DIR',str(directory))
    identifier=register(client)
    response=client.put(f'/v1/connections/{identifier}/credentials',json=key_input())
    assert response.status_code==200,response.text
    for path in ['/v1/connections','/v1/audit','/v1/overview']:
        output=client.get(path).text
        assert key_input()['access_key_id'] not in output
        assert key_input()['secret_access_key'] not in output
    saved=client.get('/v1/connections').json()['items'][0]
    assert saved['status']=='PENDING' and saved['credentials_configured']
    assert vault.load(client.get('/v1/me').json()['tenant_id'],identifier,saved['credential_version'])==key_input()
    for path in directory.rglob('*'):
        if path.is_file():
            assert key_input()['secret_access_key'].encode() not in path.read_bytes()


def test_rejected_credential_body_never_echoes_secret(client):
    identifier=register(client)
    payload={**key_input(),'unknown_secret':'sensitive-invalid-value'}
    response=client.put(f'/v1/connections/{identifier}/credentials',json=payload)
    assert response.status_code==422
    assert 'sensitive-invalid-value' not in response.text
    assert key_input()['secret_access_key'] not in response.text


def test_credential_update_is_scoped_to_tenant(client):
    identifier=register(client)
    client.post('/v1/auth/logout')
    signup(client,'different@example.com')
    assert client.put(f'/v1/connections/{identifier}/credentials',json=key_input()).status_code==404


def test_temporary_keys_require_session_token(client):
    identifier=register(client)
    values=key_input();values['access_key_id']='ASIA'+'A'*16
    assert client.put(f'/v1/connections/{identifier}/credentials',json=values).status_code==422
