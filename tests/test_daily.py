"""Daily details must preserve nested data while summaries stay small."""
import json
import uuid
from datetime import date, timedelta
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from app.main import app, db


def test_daily_scope_summary_move_and_export():
    a = client()
    anon = TestClient(app)
    for url in ('/api/calendar', '/api/entries?day=2198-02-01', '/api/entries/missing'):
        assert anon.get(url).status_code == 401
    for value in ('bad', '2026-02-30', '1899-12-31', '2201-01-01', '20261016'):
        assert a.get('/api/entries', params={'day': value}).status_code == 400
    assert a.get('/api/entries?day=2198-01-01').json() == []
    base = a.get('/api/calendar').json()['stats']
    eid, other, cid, mid, emoji, tag = [uuid.uuid4().hex for _ in range(6)]
    location = {'name':'公园','city':'','address':'','lat':None,'lng':None,'source':'manual','coordinate_system':None}
    try:
        with db() as c:
            c.executemany('INSERT INTO entries VALUES(?,?,?,?,?)', [(eid,'alan','2198-02-01','A'*5000,10),(other,'partner','2198-02-02','另一日',20)])
            c.execute('INSERT INTO media(id,entry_id,kind,mime,path,thumb) VALUES(?,?,?,?,?,?)', (mid,eid,'image','image/jpeg','unused','thumb'))
            c.execute('INSERT INTO media_extras VALUES(?,?,?,?)', (mid,'display','motion','original'))
            c.execute('INSERT INTO comments VALUES(?,?,?,?,?)', (cid,eid,'partner','评论',11))
            c.execute('INSERT INTO emojis VALUES(?,?,?,?,?)', (emoji,'表情','alan','image/png',1))
            c.execute('INSERT INTO comment_emojis VALUES(?,?,?)', (cid,0,emoji))
            c.execute('INSERT INTO entry_reactions VALUES(?,?,?)', (eid,emoji,'partner'))
            c.execute('INSERT INTO comment_reactions VALUES(?,?,?)', (cid,emoji,'alan'))
            c.execute('INSERT INTO tags VALUES(?,?,?,?,?)', (tag,'测试标签',tag,'alan',1))
            c.execute('INSERT INTO entry_tags VALUES(?,?)', (eid,tag))
            c.execute('INSERT INTO entry_locations VALUES(?,?)', (eid,json.dumps(location)))
        all_records = a.get('/api/export').json()['entries']
        expected = next(e for e in all_records if e['id'] == eid)
        daily = a.get('/api/entries?day=2198-02-01').json()
        assert daily == [expected]
        assert daily[0]['comments'][0]['emojis'] and daily[0]['comments'][0]['reactions']
        assert daily[0]['media'][0]['live'] and daily[0]['tags'] and daily[0]['reactions']
        summary = a.get('/api/calendar').json()
        assert summary['stats'] == {'days':base['days']+2,'entries':base['entries']+2,'media':base['media']+1}
        day = next(d for d in summary['days'] if d['day'] == '2198-02-01')
        assert day == {'day':'2198-02-01','count':1,'excerpt':'A'*120,'cover':{'thumb':f'/media/{mid}/thumb','kind':'image'}}
        assert a.get('/api/entries/'+eid).json() == {'id':eid,'day':'2198-02-01'}
        moved = a.patch('/api/entries/'+eid, json={'day':'2198-02-02','body':'编辑后','original':{'day':expected['day'],'body':expected['body']}}, headers=HEADERS)
        assert moved.status_code == 200, moved.text
        assert a.get('/api/entries?day=2198-02-01').json() == []
        assert len(a.get('/api/entries?day=2198-02-02').json()) == 2
        assert a.get('/api/entries/'+eid).json()['day'] == '2198-02-02'
        assert next(d for d in a.get('/api/calendar').json()['days'] if d['day']=='2198-02-02')['count'] == 2
    finally:
        with db() as c:
            c.execute('DELETE FROM entries WHERE id IN (?,?)',(eid,other))
            c.execute('DELETE FROM emojis WHERE id=?',(emoji,))
            c.execute('DELETE FROM tags WHERE id=?',(tag,))
    assert a.get('/api/entries/'+eid).status_code == 404
    assert a.get('/api/calendar').json()['stats'] == base


def test_large_history_payload():
    a = client()
    ids = [uuid.uuid4().hex for _ in range(365)]
    try:
        with db() as c:
            for i, eid in enumerate(ids):
                day = (date(2197,1,1)+timedelta(days=i)).isoformat()
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(eid,'alan',day,'回忆'*2000,i))
                for j in range(3):
                    c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',(uuid.uuid4().hex,eid,'partner','评论'*400,j))
        old = a.get('/api/entries')
        overview = a.get('/api/calendar')
        daily = a.get('/api/entries?day=2197-01-01')
        assert len(daily.json()) == 1
        assert len(overview.content)+len(daily.content) < len(old.content)*0.1
        print(f'\nSynthetic history bytes: all={len(old.content)}, overview+day={len(overview.content)+len(daily.content)}')
    finally:
        with db() as c:
            c.executemany('DELETE FROM entries WHERE id=?', [(eid,) for eid in ids])
