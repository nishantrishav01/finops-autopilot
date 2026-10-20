"""Exercise the production repository with an isolated AWS emulator, never live AWS."""
import json
import pytest
import boto3
from moto import mock_aws

from services.api.cloud_store import DynamoUnit
from services.api.store import StoreConflict


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv('AWS_DEFAULT_REGION','ap-south-1')
    monkeypatch.setenv('FINOPS_TABLE','test-operations')
    monkeypatch.setenv('FINOPS_DATA_BUCKET','test-finops-data')
    with mock_aws():
        boto3.client('dynamodb').create_table(TableName='test-operations',BillingMode='PAY_PER_REQUEST',
            KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],
            AttributeDefinitions=[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}])
        boto3.client('s3').create_bucket(Bucket='test-finops-data',CreateBucketConfiguration={'LocationConstraint':'ap-south-1'})
        key = boto3.client('kms').create_key()['KeyMetadata']['Arn']
        monkeypatch.setenv('FINOPS_KMS_KEY',key)
        yield


def test_operational_roundtrip_and_tenant_isolation(cloud):
    db=DynamoUnit()
    db.put('customer-a','connection',{'id':'account','name':'a'})
    db.put('customer-b','connection',{'id':'account','name':'b'})
    db.commit()
    reader=DynamoUnit()
    assert reader.get('customer-a','connection','account')['name']=='a'
    assert reader.items('customer-b','connection')==[{'id':'account','name':'b'}]
    assert reader.get('customer-c','connection','account') is None


def test_conflicting_writes_are_atomic(cloud):
    first,second=DynamoUnit(),DynamoUnit()
    first.get('customer-a','policy','default')
    second.get('customer-a','policy','default')
    first.put('customer-a','policy',{'id':'default','value':1})
    second.put('customer-a','policy',{'id':'default','value':2})
    second.put('customer-a','audit',{'id':'second','action':'unsafe partial'})
    first.commit()
    with pytest.raises(StoreConflict): second.commit()
    reader=DynamoUnit()
    assert reader.get('customer-a','policy','default')['value']==1
    assert reader.get('customer-a','audit','second') is None


def test_query_phantom_prevents_duplicate_scope(cloud):
    first,second=DynamoUnit(),DynamoUnit()
    assert first.items('customer-a','connection')==second.items('customer-a','connection')==[]
    first.put('customer-a','connection',{'id':'one'})
    second.put('customer-a','connection',{'id':'two'})
    first.commit()
    with pytest.raises(StoreConflict): second.commit()


def test_oversized_transaction_fails_without_partial_writes(cloud):
    db=DynamoUnit()
    for number in range(100): db.put('customer-a','recommendation',{'id':str(number)})
    with pytest.raises(StoreConflict,match='atomic transaction limit'): db.commit()
    assert DynamoUnit().items('customer-a','recommendation')==[]


def test_large_payload_offloaded_to_s3(cloud):
    db=DynamoUnit()
    db.put('customer-a','snapshot',{'id':'source','raw':{'lines':['x'*1000]*500}})
    db.commit()
    saved=DynamoUnit().get('customer-a','snapshot','source')
    assert 'raw' not in saved
    assert saved['raw_key'].startswith('snapshot/tenant=customer-a/')
    assert len(json.dumps(saved))<1000


def test_queries_do_not_spend_transaction_action_per_row(cloud):
    for number in range(120):
        db=DynamoUnit();db.put('customer-a','audit',{'id':str(number)});db.commit()
    db=DynamoUnit()
    assert len(db.items('customer-a','audit'))==120
    db.put('customer-a','audit',{'id':'next'})
    db.commit()
    assert len(DynamoUnit().items('customer-a','audit'))==121
