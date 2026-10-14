import pytest
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from app.main import app, db, add_activity

@pytest.fixture(autouse=True)
def reset_activity():
    with db() as c:
        c.execute('DELETE FROM attempts')
        c.execute('DELETE FROM activities')

def post(c,body='新回忆'):
    r=c.post('/api/entries',data={'day':'2026-10-14','body':body},headers=HEADERS)
    assert r.status_code==200,r.text
    return r.json()['id']

def comment(c,eid):
    r=c.post('/api/entries/'+eid+'/comments',json={'body':'新留言'},headers=HEADERS)
    assert r.status_code==201,r.text
    return r.json()['id']

def read(c,payload):
    return c.post('/api/activities/read',json=payload,headers=HEADERS)

def test_other_person_only_and_read_persistence():
    a=client(); b=client('partner'); eid=post(a)
    assert a.get('/api/activities').json()['unread']==0
    data=b.get('/api/activities').json()
    assert data['unread']==1 and data['items'][0]['kind']=='post'
    assert b.get('/api/activities').json()['unread']==1 # Viewing log does not read it.
    nid=data['items'][0]['id']
    assert read(a,{'id':nid}).status_code==404
    assert read(b,{'id':nid}).status_code==200
    assert read(b,{'id':nid}).status_code==200
    assert client('partner').get('/api/activities').json()['unread']==0
    cid=comment(b,eid)
    data=a.get('/api/activities').json()
    assert data['unread']==1 and data['items'][0]['comment_id']==cid
    assert b.get('/api/activities').json()['unread']==0
    # Author comments on their own post also notify the other member.
    comment(a,eid)
    assert b.get('/api/activities').json()['unread']==1

def test_edits_no_alert_delete_cleanup_and_newer_read_boundary():
    a=client(); b=client('partner'); eid=post(a)
    first=b.get('/api/activities').json()
    r=a.patch('/api/entries/'+eid,json={'day':'2026-11-01','body':'改过的文字','original':{'day':'2026-10-14','body':'新回忆'}},headers=HEADERS)
    assert r.status_code==200
    data=b.get('/api/activities').json()
    assert len(data['items'])==1 and data['unread']==1
    assert data['items'][0]['day']=='2026-11-01'
    cid=comment(a,eid)
    assert read(b,{'through':first['latest_id']}).status_code==200
    assert b.get('/api/activities').json()['unread']==1 # New comment remains unread.
    assert a.delete('/api/comments/'+cid,headers=HEADERS).status_code==200
    assert b.get('/api/activities').json()['unread']==0
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    assert b.get('/api/activities').json()['items']==[]

def test_activity_pagination_auth_and_rollback():
    anon=TestClient(app)
    assert anon.get('/api/activities').status_code==401
    assert anon.post('/api/activities/read',json={'through':0},headers=HEADERS).status_code==401
    a=client(); b=client('partner'); eid=post(a)
    with db() as c:
        for i in range(60):add_activity(c,'alan','post',eid,str(i))
    first=b.get('/api/activities').json()
    second=b.get('/api/activities?before='+str(first['next_before'])).json()
    assert len(first['items'])==50 and len(second['items'])==11
    assert len({e['id'] for e in first['items']+second['items']})==61
    assert second['next_before'] is None
    assert a.post('/api/activities/read',json={'through':first['latest_id']}).status_code==403
    for payload in ({'through':True},{'through':-1},{'id':1,'through':1},[]):
        assert read(b,payload).status_code==400
    before=b.get('/api/activities').json()['latest_id']
    response=a.post('/api/entries/'+eid+'/comments',json={'body':'invalid','emoji_ids':['0'*32]},headers=HEADERS)
    assert response.status_code==400
    assert b.get('/api/activities').json()['latest_id']==before
    assert b.get('/api/activities?before=9223372036854775808').status_code==400
