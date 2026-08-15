import base64,hashlib,hmac,html,json,math,os,secrets,sqlite3,time,urllib.parse,urllib.request,uuid
from contextlib import contextmanager
from datetime import date,datetime,timezone
from fastapi import FastAPI,HTTPException,Request,Response
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse
from pages import page,HOME,HOME_JS,MEDIA,MEDIA_JS,LOGIN,LOGIN_JS,ADMIN,ADMIN_JS
app=FastAPI(); RESEND=os.getenv('RESEND_API_KEY','').strip(); NOTIFY=os.getenv('NOTIFY_EMAIL') or 'josephfkung@gmail.com'; DB=(os.getenv('DATABASE_URL') or '').strip(); AP=os.getenv('ADMIN_PASSWORD') or 'change-me'; SS=os.getenv('SESSION_SECRET') or 'dev-only-change-this-secret'; COOKIE='familieee_admin'
def pg():return DB.startswith('postgres')
@contextmanager
def dbc():
 c=(__import__('psycopg').connect(DB) if pg() else sqlite3.connect('/tmp/fam.db'));
 if not pg(): c.row_factory=sqlite3.Row
 try: cur=c.cursor();yield cur;c.commit()
 except: c.rollback();raise
 finally:c.close()
def Q(s):return s.replace('?','%s') if pg() else s
def rows(s,p=()):
 with dbc() as c:c.execute(Q(s),p);a=c.fetchall();cols=[d.name if hasattr(d,'name') else d[0] for d in c.description] if c.description else []
 return [dict(x) if isinstance(x,sqlite3.Row) else dict(zip(cols,x)) for x in a]
def one(s,p=()):
 a=rows(s,p);return a[0] if a else None
def ex(s,p=()):
 with dbc() as c:c.execute(Q(s),p)
def ser(x):return x.isoformat() if isinstance(x,(date,datetime)) else x
def sr(x):return {k:ser(v) for k,v in x.items()}
def init():
 if pg():
  with dbc() as c:
   c.execute("""CREATE TABLE IF NOT EXISTS familieee_submissions(id text PRIMARY KEY,family_name text NOT NULL,submitter_name text NOT NULL,submitter_email text,event_title text NOT NULL,event_date date NOT NULL,event_type text NOT NULL DEFAULT 'social',description text NOT NULL,member_count integer NOT NULL DEFAULT 0,fam_head_present boolean NOT NULL DEFAULT false,advertised_beforehand boolean NOT NULL DEFAULT false,location_text text,location_display text,latitude double precision,longitude double precision,photo_data text NOT NULL,photo_filename text,photo_mime text,status text NOT NULL DEFAULT 'pending',points_awarded integer NOT NULL DEFAULT 0,reviewer_note text,submitted_at timestamptz NOT NULL DEFAULT now(),reviewed_at timestamptz)""")
   for z in ['location_text text','location_display text','latitude double precision','longitude double precision']:c.execute('ALTER TABLE familieee_submissions ADD COLUMN IF NOT EXISTS '+z)
   c.execute('CREATE TABLE IF NOT EXISTS familieee_geocode_cache(query_key text PRIMARY KEY,location_display text NOT NULL,latitude double precision NOT NULL,longitude double precision NOT NULL,created_at timestamptz NOT NULL DEFAULT now())')
 else:
  with dbc() as c:
   c.execute("""CREATE TABLE IF NOT EXISTS familieee_submissions(id TEXT PRIMARY KEY,family_name TEXT NOT NULL,submitter_name TEXT NOT NULL,submitter_email TEXT,event_title TEXT NOT NULL,event_date TEXT NOT NULL,event_type TEXT NOT NULL DEFAULT 'social',description TEXT NOT NULL,member_count INTEGER NOT NULL,fam_head_present INTEGER,advertised_beforehand INTEGER,location_text TEXT,location_display TEXT,latitude REAL,longitude REAL,photo_data TEXT NOT NULL,photo_filename TEXT,photo_mime TEXT,status TEXT DEFAULT 'pending',points_awarded INTEGER DEFAULT 0,reviewer_note TEXT,submitted_at TEXT,reviewed_at TEXT)""")
   c.execute('CREATE TABLE IF NOT EXISTS familieee_geocode_cache(query_key TEXT PRIMARY KEY,location_display TEXT,latitude REAL,longitude REAL,created_at TEXT)')
init()
def sig(v):return base64.urlsafe_b64encode(hmac.new(SS.encode(),v.encode(),hashlib.sha256).digest()).decode().rstrip('=')
def tok():p=f'{int(time.time())}.{secrets.token_urlsafe(10)}';return p+'.'+sig(p)
def ok(r):
 try:a,b,c=r.cookies.get(COOKIE,'').split('.',2);p=a+'.'+b;return hmac.compare_digest(c,sig(p)) and int(time.time())-int(a)<43200
 except:return False
def need(r):
 if not ok(r):raise HTTPException(401,'Admin login required')
def geo(loc):
 loc=' '.join(loc.split());key=loc.casefold();c=one('SELECT latitude,longitude,location_display FROM familieee_geocode_cache WHERE query_key=?',(key,))
 if c:return float(c['latitude']),float(c['longitude']),c['location_display']
 q=urllib.parse.urlencode({'q':loc,'format':'jsonv2','limit':1});req=urllib.request.Request('https://nominatim.openstreetmap.org/search?'+q,headers={'User-Agent':'UCLA-IEEE-FamilIEEEs/1.0 (https://ieee-fam-web.vercel.app)','Referer':'https://ieee-fam-web.vercel.app/'})
 try:
  with urllib.request.urlopen(req,timeout=8) as r:d=json.loads(r.read().decode())
 except Exception as e:raise HTTPException(503,'Location verification is temporarily unavailable. Please try again.') from e
 if not d:raise HTTPException(400,"We couldn't verify that location. Try a full street address or specific venue plus city.")
 a,b=float(d[0]['lat']),float(d[0]['lon']);disp=str(d[0].get('display_name') or loc)[:500];now=datetime.now(timezone.utc).isoformat()
 if pg():ex('INSERT INTO familieee_geocode_cache(query_key,location_display,latitude,longitude,created_at) VALUES(?,?,?,?,?) ON CONFLICT(query_key) DO UPDATE SET location_display=EXCLUDED.location_display,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude',(key,disp,a,b,now))
 else:ex('INSERT OR REPLACE INTO familieee_geocode_cache VALUES(?,?,?,?,?)',(key,disp,a,b,now))
 return a,b,disp
def mi(a,b,c,d):
 R=3958.7613;p1,p2=math.radians(a),math.radians(c);x=math.sin(math.radians(c-a)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(d-b)/2)**2;return 2*R*math.asin(math.sqrt(x))
def notify(row):
 if not RESEND:
  print('RESEND_API_KEY missing; notification skipped');return False
 e=lambda v:html.escape(str(v or ''));url='https://ieee-fam-web.vercel.app/admin'
 body=f'''<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#111827"><h2 style="color:#00629b">New FamilIEEE event submission</h2><p>A new event is waiting for review.</p><table style="border-collapse:collapse;width:100%;font-size:14px"><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>FamilIEEE</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['family_name'])}</td></tr><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>Event</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['event_title'])}</td></tr><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>Date</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['event_date'])}</td></tr><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>Location</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['location_text'])}</td></tr><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>Attendees</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['member_count'])}</td></tr><tr><td style="padding:8px;border-bottom:1px solid #eee"><b>Submitted by</b></td><td style="padding:8px;border-bottom:1px solid #eee">{e(row['submitter_name'])}</td></tr></table><h3>Description</h3><p style="line-height:1.6">{e(row['description'])}</p><p style="margin-top:24px"><a href="{url}" style="display:inline-block;background:#00629b;color:#fff;padding:11px 16px;border-radius:8px;text-decoration:none;font-weight:bold">Review submission</a></p></div>'''
 data=json.dumps({'from':'FamilIEEE Notifications <onboarding@resend.dev>','to':[NOTIFY],'subject':f"New FamilIEEE submission — {row['family_name']}: {row['event_title']}",'html':body}).encode()
 req=urllib.request.Request('https://api.resend.com/emails',data=data,method='POST',headers={'Authorization':'Bearer '+RESEND,'Content-Type':'application/json','Idempotency-Key':'familieee-submission-'+row['id'],'User-Agent':'IEEE-FamilIEEEs-App/1.0'})
 try:
  with urllib.request.urlopen(req,timeout=8) as r:return 200<=r.status<300
 except Exception as x:
  print('Submission saved, email notification failed:',repr(x));return False
@app.get('/',response_class=HTMLResponse)
def home():return page('FamilIEEEs — Event Check-In',HOME,HOME_JS)
@app.get('/media',response_class=HTMLResponse)
def media():return page('FamilIEEEs — Fam Feed',MEDIA,MEDIA_JS)
@app.get('/admin/login',response_class=HTMLResponse)
def login(r:Request):return RedirectResponse('/admin',302) if ok(r) else page('FamilIEEEs Admin',LOGIN,LOGIN_JS)
@app.get('/admin',response_class=HTMLResponse)
def admin(r:Request):return page('FamilIEEEs Admin',ADMIN,ADMIN_JS) if ok(r) else RedirectResponse('/admin/login',302)
@app.get('/health')
def health():return {'ok':True,'database':'postgres' if pg() else 'sqlite','email_notifications':bool(RESEND),'notification_recipient':NOTIFY}
@app.post('/api/submissions')
async def submit(r:Request):
 b=await r.json();req=['family_name','submitter_name','event_title','event_date','location_text','description','photo_data'];miss=[k for k in req if not str(b.get(k,'')).strip()]
 if miss:raise HTTPException(400,'Missing required fields: '+', '.join(miss))
 photo=str(b['photo_data']);
 if not photo.startswith('data:image/'):raise HTTPException(400,'Photo must be an image')
 if len(photo)>1800000:raise HTTPException(413,'Photo is too large')
 try:ed=datetime.fromisoformat(str(b['event_date'])).date().isoformat()
 except:raise HTTPException(400,'Invalid event date')
 fam=str(b['family_name']).strip()[:120];loc=' '.join(str(b['location_text']).split())[:300];same=rows("SELECT event_title,latitude,longitude FROM familieee_submissions WHERE lower(trim(family_name))=lower(trim(?)) AND event_date=? AND status IN ('pending','approved') ORDER BY submitted_at",(fam,ed))
 if len(same)>=2:raise HTTPException(409,'This FamilIEEE already has two pending/approved events on that date. The daily maximum is two.')
 lat,lon,disp=geo(loc);dist=None
 if same:
  if same[0]['latitude'] is None:raise HTTPException(409,'The first event on that date has no verified location. Ask an admin before submitting a second event.')
  dist=mi(lat,lon,float(same[0]['latitude']),float(same[0]['longitude']))
  if dist<2:raise HTTPException(409,f'A second event on the same day must be at least 2 miles from the first. These locations are about {dist:.2f} miles apart.')
 try:n=max(0,min(int(b.get('member_count',0)),100))
 except:n=0
 sid=str(uuid.uuid4());now=datetime.now(timezone.utc).isoformat();vals=(sid,fam,str(b['submitter_name'])[:120],None,str(b['event_title'])[:160],ed,str(b.get('event_type','social'))[:40],str(b['description'])[:1800],n,bool(b.get('fam_head_present')),bool(b.get('advertised_beforehand')),loc,disp,lat,lon,photo,'photo.jpg','image/jpeg',now)
 ex('INSERT INTO familieee_submissions(id,family_name,submitter_name,submitter_email,event_title,event_date,event_type,description,member_count,fam_head_present,advertised_beforehand,location_text,location_display,latitude,longitude,photo_data,photo_filename,photo_mime,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',vals);sent=notify({'id':sid,'family_name':fam,'submitter_name':str(b['submitter_name'])[:120],'event_title':str(b['event_title'])[:160],'event_date':ed,'location_text':loc,'member_count':n,'description':str(b['description'])[:1800]});return {'ok':True,'id':sid,'location_display':disp,'same_day_distance_miles':round(dist,2) if dist is not None else None,'notification_sent':sent}
@app.get('/api/leaderboard')
def leaders():return {'leaderboard':[sr(x) for x in rows("SELECT family_name,COALESCE(SUM(points_awarded),0) points,COUNT(*) approved_events FROM familieee_submissions WHERE status='approved' GROUP BY family_name ORDER BY points DESC,approved_events DESC,family_name")]}
@app.get('/api/media')
def feed(limit:int=18,offset:int=0,family:str=''):
 limit=max(1,min(limit,48));offset=max(0,offset);cl='';p=[]
 if family.strip():cl=' AND family_name=?';p.append(family.strip())
 p += [limit+1,offset];a=rows(f"SELECT id,family_name,event_title,event_date,event_type,description,member_count,points_awarded,location_text FROM familieee_submissions WHERE status='approved'{cl} ORDER BY event_date DESC,reviewed_at DESC LIMIT ? OFFSET ?",tuple(p));more=len(a)>limit;a=a[:limit];return {'events':[sr(x) for x in a],'has_more':more,'next_offset':offset+len(a)}
@app.get('/api/media/{sid}/photo')
def pic(sid:str):
 x=one("SELECT photo_data,photo_mime FROM familieee_submissions WHERE id=? AND status='approved'",(sid,));
 if not x:raise HTTPException(404,'Photo not found')
 return Response(base64.b64decode(x['photo_data'].split(',',1)[1]),media_type=x.get('photo_mime') or 'image/jpeg',headers={'Cache-Control':'public,max-age=3600'})
@app.post('/api/admin/login')
async def loginapi(r:Request):
 b=await r.json();
 if not hmac.compare_digest(str(b.get('password','')),AP):raise HTTPException(401,'Incorrect password')
 z=JSONResponse({'ok':True});z.set_cookie(COOKIE,tok(),max_age=43200,httponly=True,secure=os.getenv('VERCEL')=='1',samesite='lax',path='/');return z
@app.post('/api/admin/logout')
def logout():z=JSONResponse({'ok':True});z.delete_cookie(COOKIE,path='/');return z
@app.get('/api/admin/submissions')
def subs(r:Request):need(r);return {'submissions':[sr(x) for x in rows('SELECT * FROM familieee_submissions ORDER BY submitted_at DESC')]}
@app.patch('/api/admin/submissions/{sid}')
async def review(sid:str,r:Request):
 need(r);b=await r.json();st=str(b.get('status','')).lower();
 if st not in {'approved','denied','pending'}:raise HTTPException(400,'Invalid status')
 try:p=max(0,min(int(b.get('points_awarded',0)),999))
 except:p=0
 if st!='approved':p=0
 note=str(b.get('reviewer_note',''))[:1000] or None;rt=datetime.now(timezone.utc).isoformat() if st!='pending' else None;ex('UPDATE familieee_submissions SET status=?,points_awarded=?,reviewer_note=?,reviewed_at=? WHERE id=?',(st,p,note,rt,sid));return {'ok':True}
@app.delete('/api/admin/submissions/{sid}')
def delete_submission(sid:str,r:Request):
 need(r);x=one('SELECT id FROM familieee_submissions WHERE id=?',(sid,))
 if not x:raise HTTPException(404,'Submission not found')
 ex('DELETE FROM familieee_submissions WHERE id=?',(sid,));return {'ok':True}
