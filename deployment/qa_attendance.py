"""Verify attendee editing on an isolated copy, including authorization."""
from qa_reliability import build_test_app, request
from attendance_admin import install

def main():
    scope, notices = build_test_app()
    app = scope['app']
    install(app)
    payload = {'family_name':'Bits and Bites','submitter_name':'Isolated QA','event_title':'Quest QA','event_date':'2026-10-01','location_text':'Sender One','description':'Isolated test','photo_data':'data:image/jpeg;base64,/9j/2Q==','member_count':9,'fam_head_present':True,'advertised_beforehand':True}
    code, created = request(app, '/api/submissions', 'POST', payload)
    assert code == 200, (code, created)
    sid = created['id']
    auth = {'Cookie': scope['COOKIE_NAME']+'='+scope['admin_token']()}
    assert request(app, '/api/admin/submissions/'+sid, 'PATCH', {'status':'approved','points_awarded':10,'reviewer_note':'Preserve this note'}, auth)[0] == 200
    route = '/api/admin/submissions/'+sid+'/attendees'
    assert request(app, route, 'PATCH', {'member_count':8})[0] == 401
    assert request(app, '/admin/attendees/'+sid)[0] == 401
    before = scope['fetch_all']('SELECT * FROM familieee_submissions')[0]
    for value in [-1,101,8.5,'8',True,None]:
        assert request(app, route, 'PATCH', {'member_count':value}, auth)[0] == 400
    assert request(app, route, 'PATCH', b'{', auth)[0] == 400
    assert request(app, route, 'PATCH', [], auth)[0] == 400
    assert request(app, '/api/admin/submissions/missing/attendees','PATCH',{'member_count':8},auth)[0] == 404
    assert request(app, route, 'PATCH', {'member_count':8}, auth) == (200, {'ok':True,'id':sid,'member_count':8})
    after = scope['fetch_all']('SELECT * FROM familieee_submissions')[0]
    assert after['member_count'] == 8
    assert {k:v for k,v in before.items() if k!='member_count'} == {k:v for k,v in after.items() if k!='member_count'}
    assert request(app, '/api/media')[1]['events'][0]['member_count'] == 8
    assert request(app, '/api/leaderboard')[1]['leaderboard'][0]['points'] == 10
    code, page = request(app, '/admin/attendees/'+sid, headers=auth)
    assert code == 200 and 'value="8"' in page and 'Save attendees' in page
    code, page = request(app, '/admin', headers=auth)
    assert code == 200 and 'data-attendee-edit' in page
    print('QA_ATTENDANCE_PASS authorization, validation, 9-to-8 correction, feed, unchanged points and notes, admin links', flush=True)

if __name__=='__main__':main()
