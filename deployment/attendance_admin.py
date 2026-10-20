"""Admin-only attendee corrections; preserve approval, points, and review notes."""
import html
import inspect
import json
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

def install(app):
    listing = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/api/admin/submissions' and 'GET' in (getattr(r, 'methods', None) or set()))
    scope = listing.__globals__

    async def authorized_rows(request):
        result = await run_in_threadpool(listing, request, status='all')
        if inspect.isawaitable(result):
            result = await result
        return result['submissions']

    @app.patch('/api/admin/submissions/{submission_id}/attendees')
    async def update_attendees(submission_id: str, request: Request):
        all_rows = await authorized_rows(request)
        current = next((r for r in all_rows if r['id'] == submission_id), None)
        if current is None:
            raise HTTPException(404, 'Submission not found')
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, 'Invalid JSON')
        if not isinstance(body, dict) or type(body.get('member_count')) is not int or not 0 <= body['member_count'] <= 100:
            raise HTTPException(400, 'Attendees must be a whole number from 0 to 100')
        count = body['member_count']
        def save():
            with scope['db_cursor']() as cur:
                cur.execute(scope['q']('UPDATE familieee_submissions SET member_count = ? WHERE id = ? AND member_count = ?'), (count, submission_id, current['member_count']))
                if cur.rowcount != 1:
                    raise HTTPException(409, 'Attendee count changed. Reload and try again.')
        await run_in_threadpool(save)
        return {'ok': True, 'id': submission_id, 'member_count': count}

    @app.get('/admin/attendees/{submission_id}', response_class=HTMLResponse)
    async def edit_attendees(submission_id: str, request: Request):
        all_rows = await authorized_rows(request)
        row = next((r for r in all_rows if r['id'] == submission_id), None)
        if row is None:
            raise HTTPException(404, 'Submission not found')
        title = html.escape(str(row['event_title']))
        family = html.escape(str(row['family_name']))
        day = html.escape(str(row['event_date']))
        url = json.dumps('/api/admin/submissions/' + submission_id + '/attendees').replace('<', '\\u003c')
        content = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Edit attendees — FamilIEEE</title>
<style>body{font:17px system-ui;background:#f4f7fb;color:#10283d;margin:0}main{max-width:620px;margin:65px auto;background:white;padding:32px;border-radius:16px}a{color:#00629b}h1{font-size:26px}label{display:block;margin:25px 0 8px}input{font:inherit;padding:10px;width:110px}button{font:inherit;background:#00629b;color:white;border:0;border-radius:8px;padding:12px 20px;cursor:pointer;margin-left:12px}#msg{min-height:25px}small{display:block;color:#526274;margin-top:18px}</style><main><a href="/admin">← Admin queue</a><h1>""" + title + """</h1><p>""" + family + ' · ' + day + """</p><form id="edit"><label for="count">Attendees</label><input id="count" name="member_count" type="number" min="0" max="100" step="1" required value="__COUNT__"><button type="submit">Save attendees</button><small>Points awarded: """ + str(row['points_awarded']) + """</small><p id="msg" role="status"></p></form></main><script>
const form=document.getElementById('edit'),count=document.getElementById('count'),msg=document.getElementById('msg'),button=form.querySelector('button');form.onsubmit=async e=>{e.preventDefault();if(button.disabled)return;button.disabled=true;msg.textContent='Saving…';try{const r=await fetch(""" + url + """,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_count:Number(count.value)})});let d;try{d=await r.json()}catch{throw Error('Could not confirm save. Please reload before trying again.')}if(!r.ok)throw Error(d.detail||'Could not save');count.value=d.member_count;msg.textContent='Saved: '+d.member_count+' attendees'}catch(e){msg.textContent=e.message}finally{button.disabled=false}};
</script></html>"""
        return HTMLResponse(content.replace('__COUNT__', str(row['member_count'])), headers={'Cache-Control': 'no-store'})

    @app.middleware('http')
    async def edit_links(request, call_next):
        response = await call_next(request)
        if request.url.path != '/admin' or response.status_code != 200:
            return response
        body = b''.join([chunk async for chunk in response.body_iterator]).decode()
        script = """<script>(()=>{function links(){document.querySelectorAll('input[id^="p-"]').forEach(el=>{if(el.parentElement.querySelector('[data-attendee-edit]'))return;const a=document.createElement('a');a.dataset.attendeeEdit='true';a.href='/admin/attendees/'+encodeURIComponent(el.id.slice(2));a.textContent='Edit attendees';a.style.cssText='display:inline-block;margin:10px 12px';el.parentElement.append(a)})}new MutationObserver(links).observe(document.body,{childList:true,subtree:true});links()})();</script>"""
        body = body.replace('</body>', script + '</body>') if '</body>' in body else body + script
        headers = {k: v for k, v in response.headers.items() if k.lower() not in {'content-length','content-type','content-encoding'}}
        headers['Cache-Control'] = 'no-store'
        return HTMLResponse(body, status_code=response.status_code, headers=headers)
