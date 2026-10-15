"""Exercise the deployed AST against an isolated database; never import live settings."""
import ast
import asyncio
import concurrent.futures
import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from location_patch import patch_application
from submission_reliability import install


def build_test_app():
    tree = patch_application(Path('legacy_app.py').read_text())
    settings = {'DATABASE_URL': '', 'RESEND_API_KEY': '', 'ADMIN_PASSWORD': 'isolated-qa',
                'SESSION_SECRET': 'isolated-qa-only-session-secret'}
    db_path = tempfile.mktemp(prefix='familieee-qa-', suffix='.db')

    class Isolate(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id in settings for t in node.targets):
                name = next(t.id for t in node.targets if isinstance(t, ast.Name) and t.id in settings)
                node.value = ast.Constant(settings[name])
                return node
            return self.generic_visit(node)

        def visit_Constant(self, node):
            if node.value == '/tmp/familieee_local.db':
                return ast.copy_location(ast.Constant(db_path), node)
            return node

    scope = {'__name__': 'isolated_qa', '__file__': str(Path('legacy_app.py').resolve())}
    exec(compile(ast.fix_missing_locations(Isolate().visit(tree)), 'isolated_legacy.py', 'exec'), scope)
    assert not scope['using_postgres']()
    assert scope['DATABASE_URL'] == '' and scope['RESEND_API_KEY'] == ''
    calls = []
    scope['send_submission_notification'] = lambda row: calls.append(row['id']) or True
    install(scope['app'])
    return scope, calls


def request(app, path, method='GET', body=None, headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b''

    async def go():
        sent = False
        messages = []
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': raw, 'more_body': False}
            await asyncio.Event().wait()
        async def send(message):
            messages.append(message)
        await app({'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                   'http_version': '1.1', 'method': method, 'scheme': 'https', 'path': path,
                   'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
                   'headers': [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
                   'client': ('127.0.0.1', 1234), 'server': ('test', 443)}, receive, send)
        status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        try: data = json.loads(data)
        except ValueError: data = data.decode()
        return status, data
    return asyncio.run(go())


def main():
    scope, notices = build_test_app()
    app = scope['app']
    route = '/api/submissions'
    base = {'family_name': 'Mixed Signal', 'submitter_name': 'Isolated QA', 'event_title': 'First event',
            'event_date': '2026-10-01', 'location_text': 'A room with no map match', 'description': 'Test',
            'photo_data': 'data:image/jpeg;base64,/9j/2Q==', 'member_count': 4,
            'fam_head_present': True, 'advertised_beforehand': True}
    checks = []
    def passed(name): checks.append(name);print('QA_PASS', name, flush=True)
    for name, body in [('invalid JSON', b'{'), ('array body', []), ('null body', b'null'),
                       ('null required field', {**base, 'description': None}),
                       ('wrong field type', {**base, 'event_title': {}})]:
        status, result = request(app, route, 'POST', body)
        assert status == 400 and isinstance(result.get('detail'), str), (name, status, result)
    passed('malformed JSON and invalid types return JSON 400')
    for field, value, expected in [('photo_data', 'bad', 400), ('photo_data', 'data:image/jpeg;base64,'+'A'*1800001, 413), ('event_date', 'bad', 400)]:
        assert request(app, route, 'POST', {**base, field: value})[0] == expected
    passed('photo size, photo prefix, and date validation retained')
    def create(i): return request(app, route, 'POST', base, {'Idempotency-Key': 'same-retry'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: results = list(pool.map(create, range(12)))
    assert all(s == 200 for s, _ in results), results
    assert len({r['id'] for _, r in results}) == 1
    assert sum(not r['duplicate'] for _, r in results) == 1
    assert len(notices) == 1
    passed('12 concurrent retries create one row and one notification')
    first_id = results[0][1]['id']
    assert request(app, route, 'POST', base)[1]['id'] == first_id
    assert request(app, route, 'POST', base, {'Idempotency-Key': 'new-retry'})[1]['id'] == first_id
    assert request(app, route, 'POST', {**base, 'description': 'Different'}, {'Idempotency-Key': 'same-retry'})[0] == 409
    passed('identical payload retries deduplicate and reused keys cannot change content')
    def distinct(i): return request(app, route, 'POST', {**base, 'event_title': 'Different event '+str(i)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool: many=list(pool.map(distinct, range(10)))
    assert sum(s == 200 for s, _ in many) == 1, many
    assert sum(s == 409 for s, _ in many) == 9, many
    assert len(scope['fetch_all']('SELECT * FROM familieee_submissions')) == 2
    assert request(app, route, 'POST', base)[0] == 200
    passed('daily cap stays at two under 10 concurrent distinct submissions; retries still work at cap')
    assert request(app, '/api/admin/submissions')[0] == 401
    auth = {'Cookie': scope['COOKIE_NAME']+'='+scope['admin_token']()}
    status, listing = request(app, '/api/admin/submissions', headers=auth)
    assert status == 200 and len(listing['submissions']) == 2
    status, result = request(app, '/api/admin/submissions/'+first_id, 'PATCH', {'status':'approved','points_awarded':4,'reviewer_note':'QA'}, auth)
    assert status == 200, (status, result)
    assert request(app, '/api/leaderboard')[1]['leaderboard'][0]['points'] == 4
    assert len(request(app, '/api/media')[1]['events']) == 1
    scope['init_db']()
    assert len(scope['fetch_all']('SELECT * FROM familieee_submissions')) == 2
    passed('save to admin approval to feed and score; reinitialization preserves rows')
    def fail_email(row): raise RuntimeError('simulated notification outage')
    scope['send_submission_notification'] = fail_email
    status, result = request(app, route, 'POST', {**base, 'event_date':'2026-10-02'})
    assert status == 200 and result['notification_sent'] is False
    passed('notification failure cannot turn a saved submission into a failed request')
    status, html = request(app, '/')
    assert status == 200 and 'if(submitting)return' in html and 'finally{submitting=false' in html
    passed('served form contains click guard and error recovery')
    print('QA_COMPLETE',len(checks),'groups passed; all data and email isolated',flush=True)

if __name__ == '__main__': main()
