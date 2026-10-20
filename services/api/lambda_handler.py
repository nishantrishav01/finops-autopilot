"""API adapter and durable Step Functions worker entry points."""
from mangum import Mangum
from .main import app, run_job

handler = Mangum(app, lifespan='off')


def worker(event, context):
    # Step Functions owns execution; never replay a completed job or a paid AI call.
    from .store import database, get, put, now
    with database() as db:
        job = get(db, event['tenant'], 'job', event['job_id'])
        if not job or job['status'] in ('SUCCEEDED', 'PARTIAL', 'FAILED'):
            return {'status': job['status'] if job else 'MISSING'}
        if job['status'] == 'RUNNING':
            job.update(status='FAILED', error='Worker interrupted. Create a new request after reviewing its source state.', ended_at=now())
            put(db, event['tenant'], 'job', job)
            return {'status': 'FAILED'}
    run_job(event['tenant'], event['job_id'])
    return {'status': 'COMPLETE'}


def workflow_failed(event, context):
    from .store import database, get, put, now
    with database() as db:
        job = get(db, event['tenant'], 'job', event['job_id'])
        if job and job['status'] in ('QUEUED', 'RUNNING'):
            job.update(status='FAILED', error='Cloud workflow interrupted or timed out. Review the source before creating another request.', ended_at=now())
            put(db, event['tenant'], 'job', job)
    return {'status': 'FAILED'}


def dispatch(event, context):
    import json
    import os
    from .cloud_store import client
    from botocore.exceptions import ClientError
    failures = []
    for record in event['Records']:
        try:
            image = record['dynamodb'].get('NewImage', {})
            if record['eventName'] != 'INSERT' or not image.get('sk', {}).get('S', '').startswith('job#'):
                continue
            job = json.loads(image['data']['S'])
            if job['status'] != 'QUEUED':
                continue
            tenant = image['pk']['S'].removeprefix('TENANT#')
            try:
                client('stepfunctions').start_execution(stateMachineArn=os.environ['FINOPS_WORKFLOW'],
                    name=job['id'], input=json.dumps({'tenant': tenant, 'job_id': job['id']}))
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'ExecutionAlreadyExists':
                    raise
        except Exception:
            failures.append({'itemIdentifier': record['dynamodb']['SequenceNumber']})
    return {'batchItemFailures': failures}
