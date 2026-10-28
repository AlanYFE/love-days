import uuid
import pytest
from fastapi.testclient import TestClient
from test_app import app, db, client, HEADERS

TOKEN='whale-test-token-'+'x'*40
AGENT={**HEADERS,'Authorization':'Bearer '+TOKEN}

@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    monkeypatch.setenv('WHALE_API_TOKEN',TOKEN)
    with db() as c:
        c.execute('DELETE FROM whale_messages')
    yield
    with db() as c:
        c.execute('DELETE FROM whale_messages')


def test_agent_token_is_scoped_and_revocable(monkeypatch):
    anon=TestClient(app)
    assert anon.get('/api/whale/agent/entries').status_code==401
    assert client().get('/api/whale/agent/entries').status_code==401
    assert anon.get('/api/whale/agent/entries',headers=AGENT).status_code==200
    for path in ('/api/entries','/api/export','/api/me','/api/whale/messages'):
        assert anon.get(path,headers=AGENT).status_code==401
    assert anon.post('/api/entries',headers=AGENT,data={'body':'bad','day':'2026-10-28'}).status_code==401
    monkeypatch.setenv('WHALE_API_TOKEN','')
    assert anon.get('/api/whale/agent/entries',headers=AGENT).status_code==503
    assert client().post('/api/whale/messages',headers=HEADERS,json={'body':'hi','client_id':uuid.uuid4().hex}).status_code==503


def test_feed_pagination_full_text_and_no_private_account_fields():
    a=TestClient(app)
    ids=[uuid.uuid4().hex for _ in range(3)]
    cid,tag,media=[uuid.uuid4().hex for _ in range(3)]
    try:
        with db() as c:
            c.executemany('INSERT INTO entries VALUES(?,?,?,?,?)',[(eid,'alan','2196-02-01','测试帖子',123+i) for i,eid in enumerate(ids)])
            c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',(cid,ids[2],'partner','评论',1))
            c.execute('INSERT INTO tags VALUES(?,?,?,?,?)',(tag,'whale-tag',tag,'alan',1))
            c.execute('INSERT INTO entry_tags VALUES(?,?)',(ids[2],tag))
            c.execute('INSERT INTO media VALUES(?,?,?,?,?,?)',(media,ids[2],'image','image/jpeg','PRIVATE_PATH','PRIVATE_THUMB'))
        url='/api/whale/agent/entries?day=2196-02-01&limit=2'
        data=a.get(url,headers=AGENT).json()
        assert [e['id'] for e in data['entries']]==[ids[2],ids[1]]
        first=data['entries'][0]
        assert first['comments'][0]['body']=='评论' and first['tags']==['whale-tag'] and first['media_count']==1
        assert set(first)=={'id','day','body','created','author','tags','comments','media_count'}
        assert 'PRIVATE_PATH' not in str(data) and 'password' not in str(data)
        page=a.get(url+'&before='+data['next_before'],headers=AGENT).json()
        assert [e['id'] for e in page['entries']]==[ids[0]] and page['next_before'] is None
        for query in ('day=bad','day=2026-02-30','limit=0','limit=21','before=missing'):
            assert a.get('/api/whale/agent/entries?'+query,headers=AGENT).status_code==400
    finally:
        with db() as c:
            c.executemany('DELETE FROM entries WHERE id=?',[(i,) for i in ids])
            c.execute('DELETE FROM tags WHERE id=?',(tag,))


def test_shared_chat_idempotency_and_reply_identity():
    a,b,worker=client(),client('partner'),TestClient(app)
    p={'body':'hello','client_id':uuid.uuid4().hex}
    mid=a.post('/api/whale/messages',json=p,headers=HEADERS).json()['id']
    assert a.post('/api/whale/messages',json=p,headers=HEADERS).json()['id']==mid
    assert b.post('/api/whale/messages',json=p,headers=HEADERS).status_code==409
    assert b.get('/api/whale/messages').json()['messages'][0]['id']==mid
    assert worker.get('/api/whale/messages').status_code==401
    assert [m['id'] for m in worker.get('/api/whale/agent/inbox',headers=AGENT).json()['messages']]==[mid]
    assert worker.post(f'/api/whale/agent/reply/{mid}',json={'body':'鲸鱼的回复'},headers=HEADERS).status_code==401
    r=worker.post(f'/api/whale/agent/reply/{mid}',json={'body':'鲸鱼的回复'},headers=AGENT)
    assert r.status_code==201
    rid=r.json()['id']
    assert worker.post(f'/api/whale/agent/reply/{mid}',json={'body':'不能重复'},headers=AGENT).json()=={'id':rid,'already_replied':True}
    assert worker.get('/api/whale/agent/inbox',headers=AGENT).json()=={'messages':[]}
    response=b.get('/api/whale/messages').json()['messages'][-1]
    assert response['user_id'] is None and response['author']=='小鲸鱼'
    assert worker.post(f'/api/whale/agent/reply/{rid}',json={'body':'不能自循环'},headers=AGENT).status_code==404
    assert len(worker.get('/api/whale/agent/history',headers=AGENT).json()['messages'])==2


def test_validation_csrf_and_queue_bound():
    a=client()
    for p in ([],{}, {'body':''},{'body':123},{'body':'x'*4001,'client_id':uuid.uuid4().hex}):
        assert a.post('/api/whale/messages',json=p,headers=HEADERS).status_code==400
    assert a.post('/api/whale/messages',content='x'*17000,headers=HEADERS).status_code==413
    p={'body':'hi','client_id':uuid.uuid4().hex}
    assert a.post('/api/whale/messages',json=p).status_code==403
    for _ in range(20):
        assert a.post('/api/whale/messages',json={'body':'hi','client_id':uuid.uuid4().hex},headers=HEADERS).status_code==201
    assert a.post('/api/whale/messages',json=p,headers=HEADERS).status_code==429
    assert a.get('/whale').status_code==200
    assert a.get('/static/whale.js').status_code==200
