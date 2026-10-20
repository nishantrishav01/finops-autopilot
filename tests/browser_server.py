"""Isolated browser-test server. Not included in the Lambda deployment asset."""
from fastapi import Response
from services.api.main import app, issue_session, password_hash
from services.api.store import database, items
from .seed_fixture import seed_tenant, seed_connection


@app.post('/test/fixture-session')
def fixture_session(response: Response):
    with database() as db:
        db.execute("INSERT OR IGNORE INTO tenants VALUES('tenant-demo','Northstar Technologies')")
        db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?)',
            ('user-demo','tenant-demo','demo@finops.local','Test Admin',password_hash('test-fixture-password'),'admin'))
        seed_tenant(db,'tenant-demo')
        issue_session(db,'user-demo',response)
    return {'ok':True}


@app.post('/test/refresh-fixture')
def refresh_fixture():
    with database() as db:
        for connection in items(db,'tenant-demo','connection'):
            seed_connection(db,'tenant-demo',connection)
    return {'status': 'SUCCEEDED'}

# Production mounts the built static application last. Keep it last in this test harness too.
from starlette.routing import Mount
static = next((route for route in app.router.routes if isinstance(route, Mount) and route.path == ''), None)
if static:
    app.router.routes.remove(static)
    app.router.routes.append(static)
