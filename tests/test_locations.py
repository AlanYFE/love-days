import json
import pytest
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from app.main import app, db

@pytest.fixture(autouse=True)
def clear_attempts():
    with db() as c:
        c.execute('DELETE FROM attempts')

def find(c,eid):
    return next(e for e in c.get('/api/entries').json() if e['id']==eid)

def edit(c,entry,**changes):
    return c.patch('/api/entries/'+entry['id'],json={'day':entry['day'],'body':entry['body'],'location':entry['location'],'original':{'day':entry['day'],'body':entry['body'],'location':entry['location']},**changes},headers=HEADERS)

def test_location_lifecycle_and_conflict():
    a=client(); b=client('partner')
    location={'name':'平江路','city':'苏州'}
    r=a.post('/api/entries',data={'day':'2026-10-14','body':'散步','location':json.dumps(location),'tag_ids':'[]','live_options':'[]'},headers=HEADERS)
    assert r.status_code==200,r.text
    eid=r.json()['id']; original=find(a,eid)
    assert original['location']['name']=='平江路'
    assert find(b,eid)['location']==original['location']
    mapped={'name':'地图地点','city':'苏州','address':'某街道','lat':31.3,'lng':120.6,'source':'tencent','coordinate_system':'gcj02'}
    assert edit(b,original,location=mapped).status_code==403
    assert edit(a,original,location=mapped).status_code==200
    assert edit(a,original,location=None).status_code==409
    mapped_entry=find(a,eid)
    assert mapped_entry['location']==mapped
    assert next(e for e in a.get('/api/export').json()['entries'] if e['id']==eid)['location']==mapped
    # Old clients omit location: a text edit must preserve it.
    r=a.patch('/api/entries/'+eid,json={'day':original['day'],'body':'改文字','original':{'day':original['day'],'body':original['body']}},headers=HEADERS)
    assert r.status_code==200
    assert find(a,eid)['location']==mapped
    assert edit(a,find(a,eid),location=None).status_code==200
    assert find(a,eid)['location'] is None
    assert edit(a,find(a,eid),location=mapped).status_code==200
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    with db() as c:
        assert c.execute('SELECT count(*) FROM entry_locations WHERE entry_id=?',(eid,)).fetchone()[0]==0

def test_location_validation_and_private_config(monkeypatch):
    anon=TestClient(app)
    assert anon.get('/api/map-config').status_code==401
    a=client(); monkeypatch.setenv('TENCENT_MAP_KEY','test-key')
    assert a.get('/api/map-config').json()['key']=='test-key'
    assert a.get('/api/map-config').headers['cache-control']=='no-store'
    before=len(a.get('/api/entries').json())
    for value in ['bad',[],{'name':''},{'name':'a'*121},{'name':'x','lat':90},{'name':'x','lat':91,'lng':0,'source':'tencent','coordinate_system':'gcj02'},{'name':'x','lat':True,'lng':0}, {'name':'x','lat':0,'lng':0,'source':'tencent','coordinate_system':'wgs84'}]:
        response=a.post('/api/entries',data={'day':'2026-10-14','body':'test','location':json.dumps(value)},headers=HEADERS)
        assert response.status_code==400,response.text
    assert len(a.get('/api/entries').json())==before
    r=a.post('/api/entries',data={'day':'2026-10-14','body':'old client'},headers=HEADERS)
    assert r.status_code==200
    assert find(a,r.json()['id'])['location'] is None
