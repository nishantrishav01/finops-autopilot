"""Local persistence. Every operational record is partitioned by tenant."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class StoreConflict(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid4().hex}"


@contextmanager
def database():
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        from .cloud_store import DynamoUnit
        db = DynamoUnit()
        yield db
        db.commit()
        return
    path = Path(os.getenv("FINOPS_DB", "data/finops.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    if os.getenv('FINOPS_STORE') == 'dynamodb':
        return
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
          email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS entities(tenant_id TEXT NOT NULL REFERENCES tenants(id), kind TEXT NOT NULL,
          id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(tenant_id,kind,id));
        CREATE INDEX IF NOT EXISTS entities_scope ON entities(tenant_id,kind);
        ''')
        # Retire only explicitly synthetic records. Preserve real client workspaces.
        demo_users = [row['id'] for row in db.execute("SELECT id FROM users WHERE tenant_id='tenant-demo'")]
        for identifier in demo_users:
            db.execute('DELETE FROM sessions WHERE user_id=?', (identifier,))
        db.execute("DELETE FROM entities WHERE tenant_id='tenant-demo'")
        db.execute("DELETE FROM users WHERE tenant_id='tenant-demo'")
        db.execute("DELETE FROM tenants WHERE id='tenant-demo'")
        synthetic = [(row['tenant_id'], row['id']) for row in db.execute("SELECT tenant_id,id,data FROM entities WHERE kind='connection'") if json.loads(row['data']).get('mode') == 'demo']
        for tenant, identifier in synthetic:
            for row in db.execute('SELECT kind,id,data FROM entities WHERE tenant_id=?', (tenant,)).fetchall():
                value = json.loads(row['data'])
                if value.get('connection_id') == identifier or value.get('target') == identifier or (row['kind'] == 'connection' and row['id'] == identifier) or value.get('mode') == 'demo':
                    db.execute('DELETE FROM entities WHERE tenant_id=? AND kind=? AND id=?', (tenant, row['kind'], row['id']))
        # An in-process task cannot survive a process restart. Preserve its failure explicitly.
        for row in db.execute("SELECT tenant_id,id,data FROM entities WHERE kind='job'").fetchall():
            job = json.loads(row['data'])
            if job['status'] in ('QUEUED', 'RUNNING'):
                job.update(status='FAILED', error='Local process restarted; retry the operation.', ended_at=now())
                put(db, row['tenant_id'], 'job', job)
        for row in db.execute("SELECT tenant_id,data FROM entities WHERE kind='ai_usage'").fetchall():
            usage = json.loads(row['data'])
            if usage['status'] == 'RESERVED':
                usage.update(status='INTERRUPTED', ended_at=now())
                put(db, row['tenant_id'], 'ai_usage', usage)


def put(db, tenant, kind, obj):
    if hasattr(db, 'put'):
        return db.put(tenant, kind, obj)
    db.execute("INSERT INTO entities VALUES(?,?,?,?) ON CONFLICT(tenant_id,kind,id) DO UPDATE SET data=excluded.data",
               (tenant, kind, obj['id'], json.dumps(obj, separators=(',', ':'))))
    return obj


def get(db, tenant, kind, identifier):
    if hasattr(db, 'get'):
        return db.get(tenant, kind, identifier)
    row = db.execute("SELECT data FROM entities WHERE tenant_id=? AND kind=? AND id=?", (tenant, kind, identifier)).fetchone()
    return json.loads(row['data']) if row else None


def items(db, tenant, kind):
    if hasattr(db, 'items'):
        return db.items(tenant, kind)
    return [json.loads(row['data']) for row in db.execute("SELECT data FROM entities WHERE tenant_id=? AND kind=? ORDER BY id", (tenant, kind))]


def audit(db, tenant, actor, action, target, detail=''):
    return put(db, tenant, 'audit', {'id': uid('evt'), 'at': now(), 'actor': actor,
        'action': action, 'target': target, 'detail': detail})
