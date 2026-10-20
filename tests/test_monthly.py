from test_app import client, HEADERS
from app.main import app, db
from fastapi.testclient import TestClient


def test_monthly_private_drafts_versions_and_conflicts():
    a=client(); b=client('partner'); anon=TestClient(app)
    month='2196-03'
    for path in ('/api/monthly/'+month,):
        assert anon.get(path).status_code==401
        assert anon.post(path,json={'entry_ids':[]},headers=HEADERS).status_code==401
    for month_bad in ('bad','2026-13','1800-01'):
        assert a.get('/api/monthly/'+month_bad).status_code==400
    e=a.post('/api/entries',data={'day':month+'-21','body':'相遇的日子'},headers=HEADERS).json()['id']
    outside=a.post('/api/entries',data={'day':'2196-04-21','body':'下个月'},headers=HEADERS).json()['id']
    try:
        a.post('/api/entries/'+e+'/comments',json={'body':'一起收藏','emoji_ids':[]},headers=HEADERS)
        data=b.get('/api/monthly/'+month).json()
        assert data['ai_available'] is False
        assert [x['id'] for x in data['entries']]==[e]
        assert data['stats']['posts']==1 and data['stats']['comments']==1
        assert a.post('/api/monthly/'+month,json={'entry_ids':[outside]},headers=HEADERS).status_code==400
        assert a.post('/api/monthly/'+month,json={'entry_ids':[]},headers=HEADERS).status_code==400
        assert a.post('/api/monthly/'+month,json={'entry_ids':[e]}).status_code==403
        m=a.post('/api/monthly/'+month,json={'entry_ids':[e]},headers=HEADERS).json()
        assert m['payload']['origin']=='manual' and m['payload']['body']==''
        assert not m['source_changed']
        url='/api/monthly/'+month+'/'+m['id']
        payload={'revision':1,'title':'我们的三月','body':'记住这一天','note':'飞飞的话','cover_id':None,'highlights':[e],'status':'saved'}
        assert anon.put(url,json=payload,headers=HEADERS).status_code==401
        assert a.put(url,json={**payload,'cover_id':'unknown'},headers=HEADERS).status_code==400
        assert a.put(url,json={**payload,'highlights':[outside]},headers=HEADERS).status_code==400
        saved=a.put(url,json=payload,headers=HEADERS)
        assert saved.status_code==200,saved.text
        assert saved.json()['revision']==2
        assert b.put(url,json=payload,headers=HEADERS).status_code==409
        second=b.put(url,json={**payload,'revision':2,'note':'巧巧的话'},headers=HEADERS)
        assert second.status_code==200
        assert set(second.json()['payload']['notes'])=={'alan','partner'}
        another=a.post('/api/monthly/'+month,json={'entry_ids':[e]},headers=HEADERS).json()
        assert another['id']!=m['id']
        assert len(a.get('/api/monthly/'+month).json()['memories'])==2
        a.post('/api/entries/'+e+'/comments',json={'body':'新留言','emoji_ids':[]},headers=HEADERS)
        assert all(x['source_changed'] for x in a.get('/api/monthly/'+month).json()['memories'])
        a.delete('/api/entries/'+e,headers=HEADERS)
        current=b.get('/api/monthly/'+month).json()
        preserved=next(x for x in current['memories'] if x['id']==m['id'])
        assert preserved['payload']['body']=='记住这一天'
        assert preserved['source_changed'] and not current['entries']
    finally:
        with db() as c:
            c.execute('DELETE FROM monthly_memories WHERE month=?',(month,))
        a.delete('/api/entries/'+e,headers=HEADERS)
        a.delete('/api/entries/'+outside,headers=HEADERS)
