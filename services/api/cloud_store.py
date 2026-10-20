"""DynamoDB optimistic units of work and immutable S3 analytics snapshots.

Every modified record and queried collection is version checked in ONE DynamoDB
transaction. Exceeding AWS's 100-action boundary fails before any database writes.
Large billing/raw/report payloads are kept in S3, never in DynamoDB items.
"""
import copy
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError
from .store import StoreConflict

CONFIG = Config(connect_timeout=5, read_timeout=15, retries={'mode': 'standard', 'total_max_attempts': 3})


def client(service):
    return boto3.client(service, config=CONFIG)


def blob_write(key, value, jsonl=False):
    encoded = ('\n'.join(json.dumps(row, default=str, separators=(',', ':')) for row in value)+'\n') if jsonl else json.dumps(value, default=str, separators=(',', ':'))
    client('s3').put_object(Bucket=os.environ['FINOPS_DATA_BUCKET'], Key=key, Body=encoded.encode(),
        ContentType='application/x-ndjson' if jsonl else 'application/json', ServerSideEncryption='aws:kms', SSEKMSKeyId=os.environ['FINOPS_KMS_KEY'])
    return key


def blob_read(key, jsonl=False):
    with client('s3').get_object(Bucket=os.environ['FINOPS_DATA_BUCKET'], Key=key)['Body'] as body:
        value = body.read().decode()
    return [json.loads(line) for line in value.splitlines() if line] if jsonl else json.loads(value)


class DynamoUnit:
    def __init__(self):
        self.table = boto3.resource('dynamodb', config=CONFIG).Table(os.environ['FINOPS_TABLE'])
        self.reads = {}
        self.writes = {}
        self.collections = set()
        self.query_reads = set()

    @staticmethod
    def key(tenant, kind, identifier):
        # Tenant identifiers are server supplied membership data, never request fields.
        return (f'TENANT#{tenant}', f'{kind}#{identifier}')

    def raw(self, key):
        if key not in self.reads:
            value = self.table.get_item(Key={'pk': key[0], 'sk': key[1]}, ConsistentRead=True).get('Item')
            self.reads[key] = value
        return self.reads[key]

    def get(self, tenant, kind, identifier):
        key = self.key(tenant, kind, identifier)
        value = self.writes[key] if key in self.writes else self.raw(key)
        return json.loads(value['data']) if value else None

    def items(self, tenant, kind):
        if kind == 'cost':
            return [row for pointer in self.items(tenant, 'billing') for row in blob_read(pointer['key'], jsonl=True)]
        guard = self.key(tenant, '_revision', kind)
        self.raw(guard)
        self.collections.add(guard)
        pk, prefix = f'TENANT#{tenant}', f'{kind}#'
        paginator = self.table.meta.client.get_paginator('query')
        values = {}
        for page in paginator.paginate(TableName=self.table.name, ConsistentRead=True,
                KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(prefix)):
            for row in page.get('Items', []):
                key = (row['pk'], row['sk'])
                if key not in self.reads:
                    self.reads[key] = row
                    self.query_reads.add(key)
                values[key] = row
        for key, row in self.writes.items():
            if key[0] == pk and key[1].startswith(prefix):
                if row:
                    values[key] = row
                else:
                    values.pop(key, None)
        return [json.loads(row['data']) for _, row in sorted(values.items())]

    def put(self, tenant, kind, obj):
        obj = copy.deepcopy(obj)
        if kind in ('snapshot', 'report'):
            field = 'raw' if kind == 'snapshot' else 'csv'
            if field in obj:
                key = f'{kind}/tenant={tenant}/{obj["id"]}.json'
                blob_write(key, obj.pop(field))
                obj[field+'_key'] = key
        key = self.key(tenant, kind, obj['id'])
        previous = self.raw(key)
        guard = self.key(tenant, '_revision', kind)
        self.raw(guard)
        self.collections.add(guard)
        row = {'pk': key[0], 'sk': key[1], 'version': int(previous['version'])+1 if previous else 1,
               'data': json.dumps(obj, default=str, separators=(',', ':'))}
        if 'expires' in obj:
            row['expires'] = int(obj['expires'])
        if len(row['data'].encode()) > 350_000:
            raise StoreConflict('Record exceeds the deployment item-size limit; split the import.')
        self.writes[key] = row
        return obj

    def delete(self, tenant, kind, identifier):
        key = self.key(tenant, kind, identifier)
        self.raw(key)
        guard = self.key(tenant, '_revision', kind)
        self.raw(guard)
        self.collections.add(guard)
        self.writes[key] = None

    def execute(self, sql, args=()):
        if sql == 'BEGIN IMMEDIATE':
            return
        if sql == 'DELETE FROM entities WHERE tenant_id=? AND kind=? AND id=?':
            return self.delete(*args)
        raise RuntimeError('SQL is unavailable in the DynamoDB runtime.')

    def commit(self):
        if not self.writes:
            return
        changed_guards = {(key[0], '_revision#'+key[1].split('#', 1)[0]) for key in self.writes}
        serializer = TypeSerializer()
        encode = lambda row: {key: serializer.serialize(value) for key, value in row.items()}
        actions = []
        for key, previous in self.reads.items():
            condition = 'attribute_not_exists(pk)' if previous is None else '#version = :version'
            control = {'ConditionExpression': condition}
            if previous is not None:
                control.update(ExpressionAttributeNames={'#version': 'version'}, ExpressionAttributeValues={':version': serializer.serialize(previous['version'])})
            if key in self.writes:
                row = self.writes[key]
                operation = {'TableName': self.table.name, **control}
                if row is None:
                    actions.append({'Delete': {**operation, 'Key': encode({'pk': key[0], 'sk': key[1]})}})
                else:
                    actions.append({'Put': {**operation, 'Item': encode(row)}})
            elif key in changed_guards:
                row = {'pk': key[0], 'sk': key[1], 'version': int(previous['version'])+1 if previous else 1}
                actions.append({'Put': {'TableName': self.table.name, 'Item': encode(row), **control}})
            elif key in self.collections or key not in self.query_reads:
                actions.append({'ConditionCheck': {'TableName': self.table.name, 'Key': encode({'pk': key[0], 'sk': key[1]}), **control}})
        if len(actions) > 100 or len(json.dumps(actions).encode()) > 3_800_000:
            raise StoreConflict('Operation exceeds the atomic transaction limit. Reduce the batch or cloud recommendation scope; no operational records were changed.')
        try:
            # Use a plain client: resource client event handlers would double-serialize.
            client('dynamodb').transact_write_items(TransactItems=actions)
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('TransactionCanceledException', 'TransactionConflictException'):
                raise StoreConflict('Workspace changed concurrently. Refresh and retry; no partial database writes were committed.') from None
            raise
