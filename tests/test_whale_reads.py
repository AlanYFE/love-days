import base64
import io
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from PIL import Image
from test_app import app, client, db, HEADERS

AGENT = {**HEADERS, 'Authorization': 'Bearer ' + 't'*40}


def test_two_members_invite_day_then_retry_only_failed_post(monkeypatch):
    monkeypatch.setenv('WHALE_API_TOKEN','t'*40)
    a, b, worker = client(), client('partner'), TestClient(app)
    day = '2197-04-05'
    entry_ids = []
    image = io.BytesIO()
    Image.new('RGB',(23,17),'orange').save(image,'PNG')
    try:
        for body in ['第一篇','第二篇']:
            result = a.post('/api/entries', data={'day':day,'body':body},
                files={'files':('test.png',image.getvalue(),'image/png')}, headers=HEADERS)
            entry_ids.append(result.json()['id'])
        for eid in entry_ids:
            b.post(f'/api/entries/{eid}/comments',json={'body':'想说的话'},headers=HEADERS).raise_for_status()
        invite = '/api/whale/read-day/'+day
        assert worker.post(invite,headers=HEADERS).status_code == 401
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(lambda c:c.post(invite,headers=HEADERS).json()['queued'], [a,b])) == [0,2]
        claim = '/api/whale/agent/reads/claim'
        assert worker.post(claim,headers=HEADERS).status_code == 401
        def take():
            return worker.post(claim,headers=AGENT).json()['job']
        def url(job):
            return '/api/whale/agent/reads/'+job['ticket']
        first=take()
        assert first['body'] in ['第一篇','第二篇'] and first['comments'][0]['body']=='想说的话'
        assert take() is None
        preview=worker.get(url(first)+'/images/'+first['images'][0],headers=AGENT)
        assert Image.open(io.BytesIO(base64.b64decode(preview.json()['jpeg']))).size == (23,17)
        assert worker.get(url(first)+'/images/missing',headers=AGENT).status_code == 404
        for text in ['看到了！','重复提交']:
            worker.post(url(first)+'/reply',json={'body':text},headers=AGENT).raise_for_status()
        second=take()
        assert second['id'] != first['id']
        assert worker.get(url(second)+'/images/'+first['images'][0],headers=AGENT).status_code == 404
        worker.post(url(second)+'/fail',headers=AGENT).raise_for_status()
        assert b.post(invite,headers=HEADERS).json()['queued']==1
        retry=take()
        assert retry['id']==second['id'] and retry['ticket']!=second['ticket']
        assert worker.post(url(second)+'/reply',json={'body':'过期回复'},headers=AGENT).status_code==409
        worker.post(url(retry)+'/reply',json={'body':'第二条留言'},headers=AGENT).raise_for_status()
        assert a.post(invite,headers=HEADERS).json()['queued']==0 and take() is None
        entries=b.get('/api/entries?day='+day).json()
        replies = {e['id']:[c['body'] for c in e['comments'] if c.get('is_ai')] for e in entries}
        assert replies=={first['id']:['看到了！'],second['id']:['第二条留言']}
    finally:
        for eid in entry_ids:
            a.delete('/api/entries/'+eid,headers=HEADERS)
