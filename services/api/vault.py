"""Write-only onboarding credentials. Plaintext exists only in the API/collector process.

Local Windows uses CurrentUser DPAPI; cloud uses Secrets Manager. Never return
credentials, enable SDK wire logging, or send this module's values to Bedrock.
"""
import base64
import ctypes
import json
import os
from uuid import uuid4
from pathlib import Path


def _name(tenant, identifier):
    import re
    if not all(re.fullmatch(r'[A-Za-z0-9_-]+', value) for value in (tenant, identifier)):
        raise ValueError('Invalid credential scope.')
    return f'finops/{tenant}/{identifier}'


def _client():
    import boto3
    from botocore.config import Config
    return boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'ap-south-1'),
        config=Config(connect_timeout=5, read_timeout=15, retries={'mode': 'standard', 'total_max_attempts': 2}))


def _dpapi(value, entropy, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Local access-key storage requires Windows DPAPI. Use role authentication on this host.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    def blob(data):
        buffer = ctypes.create_string_buffer(data)
        return Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer
    source, source_buffer = blob(value)
    extra, entropy_buffer = blob(entropy.encode())
    output = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, ctypes.byref(extra), None, None, 1, ctypes.byref(output)):
        raise RuntimeError('Windows credential encryption failed.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)


def _path(tenant, identifier):
    _name(tenant, identifier)
    return Path(os.getenv('FINOPS_VAULT_DIR', 'data/credentials')) / tenant / (identifier+'.json')


def save(tenant, identifier, credentials):
    name = _name(tenant, identifier)
    payload = json.dumps(credentials, separators=(',', ':'))
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        from botocore.exceptions import ClientError
        client = _client()
        try:
            return client.create_secret(Name=name, SecretString=payload, KmsKeyId=os.environ['FINOPS_KMS_KEY'])['VersionId']
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'ResourceExistsException':
                raise RuntimeError('Credential storage failed.') from None
            return client.put_secret_value(SecretId=name, SecretString=payload)['VersionId']
    else:
        encrypted = _dpapi(payload.encode(), name)
        version = uuid4().hex
        path = _path(tenant, identifier+'-'+version)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 1, 'ciphertext': base64.b64encode(encrypted).decode()}), encoding='utf-8')
        os.replace(temporary, path)
        return version


def load(tenant, identifier, version=None):
    name = _name(tenant, identifier)
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        # Application runtime only. Never execute this read in agent tools or log its result.
        if not version:
            raise RuntimeError('Credential version is missing.')
        payload = _client().get_secret_value(SecretId=name, VersionId=version)['SecretString']
    else:
        encrypted = base64.b64decode(json.loads(_path(tenant, identifier+'-'+version).read_text(encoding='utf-8'))['ciphertext'])
        payload = _dpapi(encrypted, name, decrypt=True).decode()
    return json.loads(payload)
