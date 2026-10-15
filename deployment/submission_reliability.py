"""Validated submissions, transactional deduplication, and resilient form handling."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

FIELDS = [
    'id', 'family_name', 'submitter_name', 'submitter_email', 'event_title',
    'event_date', 'event_type', 'description', 'member_count', 'fam_head_present',
    'advertised_beforehand', 'photo_data', 'photo_filename', 'photo_mime',
    'submitted_at', 'location_text', 'location_display', 'latitude', 'longitude',
]
IDENTITY = [k for k in FIELDS if k not in {
    'id', 'submitted_at', 'photo_filename', 'photo_mime', 'location_display',
    'latitude', 'longitude',
}]


def validate(body, scope, key=''):
    if not isinstance(body, dict):
        raise HTTPException(400, 'Submission must be a JSON object')
    required = ['family_name', 'submitter_name', 'event_title', 'event_date',
                'location_text', 'description', 'photo_data']
    missing = [k for k in required if not isinstance(body.get(k), str) or not body[k].strip()]
    if missing:
        raise HTTPException(400, 'Missing or invalid required fields: ' + ', '.join(missing))
    photo = body['photo_data']
    if not photo.startswith('data:image/'):
        raise HTTPException(400, 'Photo must be an image')
    if len(photo) > scope['MAX_PHOTO_CHARS']:
        raise HTTPException(413, 'Photo is too large after compression')
    try:
        event_date = datetime.fromisoformat(body['event_date']).date().isoformat()
    except ValueError:
        raise HTTPException(400, 'Invalid event date')
    for field in ['fam_head_present', 'advertised_beforehand']:
        if field in body and not isinstance(body[field], bool):
            raise HTTPException(400, field + ' must be true or false')
    try:
        members = max(0, min(int(body.get('member_count', 0)), 100))
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(400, 'Invalid member count')
    for field in ['submitter_email', 'event_type', 'photo_filename']:
        if field in body and body[field] is not None and not isinstance(body[field], str):
            raise HTTPException(400, 'Invalid ' + field)
    if len(key) > 128:
        raise HTTPException(400, 'Invalid submission retry key')
    loc = body['location_text'].strip()[:300]
    row = {
        'family_name': body['family_name'].strip()[:120],
        'submitter_name': body['submitter_name'].strip()[:120],
        'submitter_email': (body.get('submitter_email') or '').strip()[:200] or None,
        'event_title': body['event_title'].strip()[:160], 'event_date': event_date,
        'event_type': (body.get('event_type') or 'social').strip()[:40] or 'social',
        'description': body['description'].strip()[:1800], 'member_count': members,
        'fam_head_present': body.get('fam_head_present', False),
        'advertised_beforehand': body.get('advertised_beforehand', False),
        'photo_data': photo, 'photo_filename': (body.get('photo_filename') or 'photo.jpg')[:255],
        'photo_mime': 'image/jpeg', 'submitted_at': datetime.now(timezone.utc).isoformat(),
        'location_text': loc, 'location_display': loc, 'latitude': None, 'longitude': None,
    }
    fingerprint = hashlib.sha256(json.dumps({k: row[k] for k in IDENTITY}, sort_keys=True).encode()).hexdigest()
    row['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'familieee-submission-v1:' + (key or fingerprint)))
    return row


def matches(a, b):
    for k in IDENTITY:
        if k in {'fam_head_present', 'advertised_beforehand'}:
            if bool(a.get(k)) != bool(b.get(k)):
                return False
        elif str(a.get(k)) != str(b.get(k)):
            return False
    return True


def read_rows(cur):
    cols = [d.name if hasattr(d, 'name') else d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def persist(row, scope):
    """One transaction owns the duplicate check, daily cap, and insert."""
    family_key = scope['normalize_family'](row['family_name'])
    pg = scope['using_postgres']()
    query = scope['q']
    with scope['db_cursor']() as cur:
        if pg:
            # Transaction locks work across processes and pooled connections.
            names = ['familieee-day:' + family_key + ':' + row['event_date'],
                     'familieee-id:' + row['id']]
            locks = sorted({int.from_bytes(hashlib.sha256(n.encode()).digest()[:8], 'big', signed=True) for n in names})
            for lock in locks:
                cur.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
        else:
            cur.execute('BEGIN IMMEDIATE')
        cur.execute(query('SELECT * FROM familieee_submissions WHERE id = ?'), (row['id'],))
        found = read_rows(cur)
        if found:
            if not matches(found[0], row):
                raise HTTPException(409, 'This retry key belongs to a different submission')
            return found[0], False
        cur.execute(query('SELECT * FROM familieee_submissions WHERE event_date = ?'), (row['event_date'],))
        existing = [r for r in read_rows(cur) if scope['normalize_family'](str(r['family_name'])) == family_key]
        # Identical retries also deduplicate clients that do not send a retry key.
        for previous in existing:
            if matches(previous, row):
                return previous, False
        active = [r for r in existing if r['status'] in ('pending', 'approved')]
        if len(active) >= scope['MAX_EVENTS_PER_DAY']:
            raise HTTPException(409, 'This FamilIEEE already has 2 pending/approved events on that date. Maximum is 2 per day.')
        cur.execute(query('INSERT INTO familieee_submissions (' + ','.join(FIELDS) + ') VALUES (' + ','.join('?' for _ in FIELDS) + ')'), tuple(row[k] for k in FIELDS))
    return row, True


def install(app):
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/api/submissions' and 'POST' in (getattr(r, 'methods', None) or set()))
    scope = route.endpoint.__globals__

    async def create_submission(request: Request):
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, 'Invalid JSON submission')
        row = validate(body, scope, request.headers.get('Idempotency-Key', ''))
        try:
            saved, created = await run_in_threadpool(persist, row, scope)
        except HTTPException:
            raise
        except Exception as exc:
            print('Submission database operation failed:', type(exc).__name__)
            raise HTTPException(503, 'Could not confirm your submission. Please retry the same event.')
        notified = False
        if created:
            try:
                notified = await run_in_threadpool(scope['send_submission_notification'], saved)
            except Exception as exc:
                print('Submission saved; notification failed:', type(exc).__name__)
        return {'ok': True, 'id': saved['id'], 'location_display': saved.get('location_display'),
                'notification_sent': bool(notified), 'duplicate': not created}

    route.endpoint = create_submission
    route.dependant.call = create_submission

    @app.middleware('http')
    async def reliable_form(request, call_next):
        response = await call_next(request)
        if request.url.path != '/' or response.status_code != 200:
            return response
        body = b''.join([chunk async for chunk in response.body_iterator]).decode()
        script = Path(__file__).with_name('submission_form.js').read_text()
        # Only replace this form's existing inline script; keep the deployed UI.
        start = body.rfind('<script>')
        end = body.find('</script>', start)
        if start < 0 or end < 0:
            raise RuntimeError('Submission form script not found')
        body = body[:start] + '<script>' + script + '</script>' + body[end + 9:]
        headers = {k: v for k, v in response.headers.items() if k.lower() not in {'content-length', 'content-type', 'content-encoding'}}
        headers['Cache-Control'] = 'no-store'
        return HTMLResponse(body, status_code=response.status_code, headers=headers)
