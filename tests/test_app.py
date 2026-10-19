import io, os, tempfile
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='blue-test-')
os.environ['PUBLIC_URL'] = 'http://testserver'
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app, db, password_hash, MEDIA

HEADERS = {'X-Blue-Request':'1','Origin':'http://testserver'}
with db() as c:
    for uid in ('alan','partner'):
        salt='11'*16
        c.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,uid,salt,password_hash('Test-password-123!',salt)))

def client(uid='alan'):
    c=TestClient(app)
    assert c.post('/api/login',json={'username':uid,'password':'Test-password-123!'},headers=HEADERS).status_code==200
    return c

def test_private_shared_upload_delete():
    anon=TestClient(app)
    assert anon.get('/api/entries').status_code==401
    a=client(); b=client('partner')
    png=io.BytesIO(); Image.new('RGB',(24,24),'blue').save(png,'PNG')
    r=a.post('/api/entries',data={'day':'2026-10-12','body':'一起去散步 <script>alert(1)</script>'},files={'files':('blue.png',png.getvalue(),'image/png')},headers=HEADERS)
    assert r.status_code==200, r.text
    eid=r.json()['id']
    e=next(e for e in b.get('/api/entries').json() if e['id']==eid)
    assert e['author']=='alan' and e['body'].endswith('</script>')
    url=e['media'][0]['url']; thumb=e['media'][0]['thumb']
    assert anon.get(url).status_code==401
    assert anon.get(thumb).status_code==401
    assert b.get(url).headers['content-type']=='image/png'
    assert b.get(thumb).status_code==200
    assert b.delete('/api/entries/'+eid,headers=HEADERS).status_code==403
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    assert b.get(url).status_code==404
    assert b.get('/api/export').json()['version']==1
    assert a.post('/api/logout',headers=HEADERS).status_code==200
    assert a.get('/api/me').status_code==401

def test_validation_and_rollback():
    a=client(); before=set(MEDIA.iterdir())
    for day,body in [('not-a-date','hi'),('2026-02-30','hi'),('2026-10-12','')]:
        r=a.post('/api/entries',data={'day':day,'body':body},headers=HEADERS)
        assert r.status_code==400, r.text
    r=a.post('/api/entries',data={'day':'2026-10-12','body':'test'},files={'files':('payload.svg',b'<svg><script>alert(1)</script></svg>','image/svg+xml')},headers=HEADERS)
    assert r.status_code==400
    assert set(MEDIA.iterdir())==before
    assert a.post('/api/entries',data={'day':'2026-10-12','body':'ok'},headers=HEADERS).status_code==200

def test_csrf_and_password():
    a=client()
    assert a.post('/api/logout').status_code==403
    assert a.post('/api/logout',headers={'X-Blue-Request':'1','Origin':'https://evil.example'}).status_code==403
    assert TestClient(app).post('/api/login',json={'username':'alan','password':'wrong'},headers=HEADERS).status_code==401

def test_health_and_bundle():
    a=TestClient(app)
    assert a.get('/').status_code==200
    assert a.get('/static/app.js').status_code==200
    assert "frame-ancestors 'none'" in a.get('/').headers['content-security-policy']

def test_video_and_range(tmp_path):
    import subprocess
    path=tmp_path/'test.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    a=client()
    r=a.post('/api/entries',data={'day':'2026-10-11','body':'视频回忆'},files={'files':('test.mp4',path.read_bytes(),'video/mp4')},headers=HEADERS)
    assert r.status_code==200, r.text
    e=next(e for e in a.get('/api/entries').json() if e['id']==r.json()['id'])
    media=e['media'][0]
    assert media['kind']=='video' and media['thumb']
    assert a.get(media['thumb']).status_code==200
    assert a.get(media['url'],headers={'Range':'bytes=0-99'}).status_code==206
    a.delete('/api/entries/'+e['id'],headers=HEADERS)


def test_comments_permissions_validation_export_and_cascade():
    a=client(); b=client('partner'); anon=TestClient(app)
    r=a.post('/api/entries',data={'day':'2026-10-12','body':'有评论的日记'},headers=HEADERS)
    eid=r.json()['id']; endpoint='/api/entries/'+eid+'/comments'
    assert anon.post(endpoint,json={'body':'hi'},headers=HEADERS).status_code==401
    assert b.post(endpoint,json={'body':'hi'}).status_code==403
    for payload in ({'body':'   '},{'body':'x'*1001},{'body':1},[],{}):
        assert b.post(endpoint,json=payload,headers=HEADERS).status_code==400
    assert b.post(endpoint,content='{',headers=HEADERS).status_code==400
    assert b.post('/api/entries/missing/comments',json={'body':'hi'},headers=HEADERS).status_code==404
    r=b.post(endpoint,json={'body':'  喜欢这一天\n<script>alert(1)</script>  '},headers=HEADERS)
    assert r.status_code==201
    comment=r.json(); cid=comment['id']
    assert comment['user_id']=='partner' and comment['body'].startswith('喜欢')
    found=next(e for e in a.get('/api/entries').json() if e['id']==eid)
    assert found['comments'][0]['id']==cid
    exported=next(e for e in a.get('/api/export').json()['entries'] if e['id']==eid)
    assert exported['comments']==found['comments']
    assert anon.delete('/api/comments/'+cid,headers=HEADERS).status_code==401
    assert a.delete('/api/comments/'+cid,headers=HEADERS).status_code==403
    assert b.delete('/api/comments/'+cid,headers=HEADERS).status_code==200
    assert b.delete('/api/comments/'+cid,headers=HEADERS).status_code==404
    cid=b.post(endpoint,json={'body':'x'*1000},headers=HEADERS).json()['id']
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    with db() as c:
        assert c.execute('SELECT 1 FROM comments WHERE id=?',(cid,)).fetchone() is None

def test_existing_database_upgrade_preserves_data(tmp_path):
    import sqlite3, subprocess, sys
    path=tmp_path/'blue.db'
    with sqlite3.connect(path) as c:
        c.executescript('CREATE TABLE users(id TEXT PRIMARY KEY,name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL); CREATE TABLE entries(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),day TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);')
        c.execute("INSERT INTO users VALUES('old','旧账号','salt','hash')")
        c.execute("INSERT INTO entries VALUES('entry','old','2026-10-01','已有回忆',1)")
    env={**os.environ,'DATA_DIR':str(tmp_path)}
    # Two independent starts verify that the migration is repeatable.
    for _ in range(2):
        subprocess.run([sys.executable,'-c','import app.main'],env=env,check=True)
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT body FROM entries').fetchone()[0]=='已有回忆'
        assert c.execute('SELECT name FROM users').fetchone()[0]=='旧账号'
        assert c.execute('SELECT count(*) FROM comments').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM tags').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM entry_tags').fetchone()[0]==0

def test_custom_emoji_and_reactions():
    from app.main import EMOJI_DIR, MAX_EMOJI_BYTES
    a=client(); b=client('partner'); anon=TestClient(app)
    assert anon.get('/api/emojis').status_code==401
    before=set(EMOJI_DIR.iterdir())
    assert anon.post('/api/emojis',headers=HEADERS).status_code==401
    for raw in (b'<svg><script>bad</script></svg>',b'GIF89anot-valid',b'x'*(MAX_EMOJI_BYTES+1)):
        r=a.post('/api/emojis',data={'name':'bad'},files={'file':('x.gif',raw,'image/gif')},headers=HEADERS)
        assert r.status_code in (400,413),r.text
    assert set(EMOJI_DIR.iterdir())==before
    gif=io.BytesIO()
    Image.new('RGB',(24,24),'blue').save(gif,'GIF',save_all=True,append_images=[Image.new('RGB',(24,24),'red')],duration=120,loop=0)
    raw=gif.getvalue()
    r=a.post('/api/emojis',data={'name':'抱抱'},files={'file':('hug.gif',raw,'image/gif')},headers=HEADERS)
    assert r.status_code==201,r.text
    emoji=r.json(); emid=emoji['id']
    assert any(e['id']==emid for e in b.get('/api/emojis').json())
    assert anon.get(emoji['url']).status_code==401
    image=b.get(emoji['url']);assert image.content==raw and image.headers['content-type']=='image/gif'
    assert Image.open(io.BytesIO(image.content)).n_frames==2
    eid=a.post('/api/entries',data={'day':'2026-10-12','body':'表情测试'},headers=HEADERS).json()['id']
    endpoint='/api/entries/'+eid+'/comments'
    for ids in ([emid]*9,['missing'],['f'*32],emid,[None]):
        assert b.post(endpoint,json={'body':'','emoji_ids':ids},headers=HEADERS).status_code==400
    r=b.post(endpoint,json={'body':'','emoji_ids':[emid,emid]},headers=HEADERS)
    assert r.status_code==201,r.text
    cid=r.json()['id']
    for kind,target in [('entries',eid),('comments',cid)]:
        url=f'/api/{kind}/{target}/reactions/{emid}'
        assert anon.put(url,json={'active':True},headers=HEADERS).status_code==401
        assert a.put(url,json={'active':True}).status_code==403
        assert a.put(url,json={'active':'true'},headers=HEADERS).status_code==400
        for _ in range(2):
            assert a.put(url,json={'active':True},headers=HEADERS).status_code==200
        assert b.put(url,json={'active':True},headers=HEADERS).status_code==200
        e=next(e for e in b.get('/api/entries').json() if e['id']==eid)
        parent=e if kind=='entries' else e['comments'][0]
        assert parent['reactions'][0]['count']==2
        assert set(parent['reactions'][0]['user_ids'])=={'alan','partner'}
        for _ in range(2):
            assert a.put(url,json={'active':False},headers=HEADERS).status_code==200
        e=next(e for e in a.get('/api/entries').json() if e['id']==eid)
        parent=e if kind=='entries' else e['comments'][0]
        assert parent['reactions'][0]['count']==1
        assert parent['reactions'][0]['user_ids']==['partner']
    e=next(e for e in a.get('/api/export').json()['entries'] if e['id']==eid)
    assert [x['id'] for x in e['comments'][0]['emojis']]==[emid,emid]
    assert a.put(f'/api/entries/missing/reactions/{emid}',json={'active':True},headers=HEADERS).status_code==404
    assert a.put(f'/api/entries/{eid}/reactions/missing',json={'active':True},headers=HEADERS).status_code==404
    assert a.delete('/api/comments/'+cid,headers=HEADERS).status_code==403
    assert b.delete('/api/comments/'+cid,headers=HEADERS).status_code==200
    with db() as c:
        assert not c.execute('SELECT 1 FROM comment_reactions WHERE target_id=?',(cid,)).fetchone()
        assert not c.execute('SELECT 1 FROM comment_emojis WHERE comment_id=?',(cid,)).fetchone()
    cid=b.post(endpoint,json={'body':'hello','emoji_ids':[emid]},headers=HEADERS).json()['id']
    b.put(f'/api/comments/{cid}/reactions/{emid}',json={'active':True},headers=HEADERS)
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    with db() as c:
        assert not c.execute('SELECT 1 FROM entry_reactions WHERE target_id=?',(eid,)).fetchone()
        assert not c.execute('SELECT 1 FROM comment_reactions WHERE target_id=?',(cid,)).fetchone()
        assert not c.execute('SELECT 1 FROM comment_emojis WHERE comment_id=?',(cid,)).fetchone()
    assert b.get(emoji['url']).status_code==200

def test_edit_entry_permissions_validation_and_preservation():
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client(); b=client('partner'); anon=TestClient(app)
    png=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(png,'PNG')
    eid=a.post('/api/entries',data={'day':'2026-10-12','body':'原文'},files={'files':('a.png',png.getvalue(),'image/png')},headers=HEADERS).json()['id']
    b.post('/api/entries/'+eid+'/comments',json={'body':'留言'},headers=HEADERS)
    before=next(e for e in a.get('/api/entries').json() if e['id']==eid)
    url='/api/entries/'+eid
    payload={'day':'2025-08-25','body':'修改后的文字','original':{'day':before['day'],'body':before['body']}}
    assert anon.patch(url,json=payload,headers=HEADERS).status_code==401
    assert b.patch(url,json=payload,headers=HEADERS).status_code==403
    assert a.patch(url,json=payload).status_code==403
    for bad in ({**payload,'day':'2026-02-30'},{**payload,'body':'x'*5001},{**payload,'body':None},[],{**payload,'day':'1800-01-01'}):
        assert a.patch(url,json=bad,headers=HEADERS).status_code==400
    assert a.patch(url,content='{',headers=HEADERS).status_code==400
    assert a.patch('/api/entries/missing',json=payload,headers=HEADERS).status_code==404
    assert a.patch(url,json=payload,headers=HEADERS).status_code==200
    after=next(e for e in b.get('/api/entries').json() if e['id']==eid)
    assert after['day']==payload['day'] and after['body']==payload['body']
    for key in ('media','comments','reactions','created','user_id'):
        assert before[key]==after[key]
    assert b.get(after['media'][0]['url']).content==png.getvalue()
    assert a.patch(url,json=payload,headers=HEADERS).status_code==409
    payload['original']={'day':after['day'],'body':after['body']};payload['body']=''
    assert a.patch(url,json=payload,headers=HEADERS).status_code==200
    eid=a.post('/api/entries',data={'day':'2026-10-12','body':'文字帖'},headers=HEADERS).json()['id']
    payload={'day':'2026-10-12','body':'  ','original':{'day':'2026-10-12','body':'文字帖'}}
    assert a.patch('/api/entries/'+eid,json=payload,headers=HEADERS).status_code==400

def test_shared_tag_library_normalization_and_privacy():
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client(); b=client('partner'); anon=TestClient(app)
    assert anon.get('/api/tags').status_code==401
    assert anon.post('/api/tags',json={'name':'散步'},headers=HEADERS).status_code==401
    assert a.post('/api/tags',json={'name':'散步'}).status_code==403
    for payload in ([],{}, {'name':None},{'name':'  '},{'name':'字'*25},{'name':'bad\x00name'}):
        assert a.post('/api/tags',json=payload,headers=HEADERS).status_code==400
    assert a.post('/api/tags',content='{',headers=HEADERS).status_code==400
    tag=a.post('/api/tags',json={'name':'  一起散步  '},headers=HEADERS)
    assert tag.status_code==201
    tag=tag.json()
    assert tag['name']=='一起散步'
    assert b.post('/api/tags',json={'name':'一起散步'},headers=HEADERS).json()==tag
    fullwidth=a.post('/api/tags',json={'name':' ＧＡＭＥ　 Night '},headers=HEADERS).json()
    assert b.post('/api/tags',json={'name':'game  night'},headers=HEADERS).json()==fullwidth
    assert tag in b.get('/api/tags').json()
    with db() as c:
        assert c.execute('SELECT count(*) FROM tags WHERE name_key=?',('game night',)).fetchone()[0]==1


def test_post_tags_create_edit_conflict_export_and_cascade():
    import json
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client(); b=client('partner')
    tags=[a.post('/api/tags',json={'name':name},headers=HEADERS).json() for name in ('电影','探店')]
    ids=[t['id'] for t in tags]
    png=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(png,'PNG')
    response=a.post('/api/entries',data={'day':'2026-10-12','body':'周末','tag_ids':json.dumps([ids[0],ids[0]])},files={'files':('a.png',png.getvalue(),'image/png')},headers=HEADERS)
    assert response.status_code==200,response.text
    eid=response.json()['id'];url='/api/entries/'+eid
    b.post(url+'/comments',json={'body':'开心'},headers=HEADERS)
    before=next(e for e in b.get('/api/entries').json() if e['id']==eid)
    assert before['tags']==[tags[0]]
    payload={'day':before['day'],'body':before['body'],'tag_ids':ids,'original':{'day':before['day'],'body':before['body'],'tag_ids':[ids[0]]}}
    assert b.patch(url,json=payload,headers=HEADERS).status_code==403
    assert a.patch(url,json=payload,headers=HEADERS).status_code==200
    after=next(e for e in b.get('/api/export').json()['entries'] if e['id']==eid)
    assert {t['id'] for t in after['tags']}==set(ids)
    for k in ('created','media','comments','reactions'):
        assert after[k]==before[k]
    # Tags-only edits must detect stale snapshots, even when body/day match.
    assert a.patch(url,json=payload,headers=HEADERS).status_code==409
    # Older clients omit tags; their text edits must not clear associations.
    legacy={'day':after['day'],'body':'新文字','original':{'day':after['day'],'body':after['body']}}
    assert a.patch(url,json=legacy,headers=HEADERS).status_code==200
    edited=next(e for e in a.get('/api/entries').json() if e['id']==eid)
    assert edited['tags']==after['tags']
    payload={'day':'2026-09-01','body':'新文字','tag_ids':['f'*32],'original':{'day':edited['day'],'body':edited['body'],'tag_ids':ids}}
    assert a.patch(url,json=payload,headers=HEADERS).status_code==400
    unchanged=next(e for e in a.get('/api/entries').json() if e['id']==eid)
    assert unchanged==edited
    payload['tag_ids']=[]
    assert a.patch(url,json=payload,headers=HEADERS).status_code==200
    cleared=next(e for e in a.get('/api/entries').json() if e['id']==eid)
    assert cleared['tags']==[] and cleared['day']=='2026-09-01'
    payload={'day':cleared['day'],'body':cleared['body'],'tag_ids':ids,'original':{'day':cleared['day'],'body':cleared['body'],'tag_ids':[]}}
    assert a.patch(url,json=payload,headers=HEADERS).status_code==200
    assert a.delete(url,headers=HEADERS).status_code==200
    with db() as c:
        assert c.execute('SELECT count(*) FROM entry_tags WHERE entry_id=?',(eid,)).fetchone()[0]==0
    assert all(t in b.get('/api/tags').json() for t in tags)


def test_tag_limits_and_invalid_create_leaves_no_media():
    import json
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client()
    ids=[a.post('/api/tags',json={'name':f'活动{i}'},headers=HEADERS).json()['id'] for i in range(9)]
    before=set(MEDIA.iterdir())
    png=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(png,'PNG')
    for value in ('{',json.dumps(None),json.dumps('oops'),json.dumps([None]),json.dumps(['f'*32]),json.dumps(ids)):
        r=a.post('/api/entries',data={'day':'2026-10-12','body':'test','tag_ids':value},files={'files':('a.png',png.getvalue(),'image/png')},headers=HEADERS)
        assert r.status_code==400,r.text
    assert set(MEDIA.iterdir())==before
    r=a.post('/api/entries',data={'day':'2026-10-12','body':'test','tag_ids':json.dumps(ids[:8])},headers=HEADERS)
    assert r.status_code==200
    e=next(e for e in a.get('/api/entries').json() if e['id']==r.json()['id'])
    assert len(e['tags'])==8
    legacy=a.post('/api/entries',data={'day':'2026-10-12','body':'没选标签'},headers=HEADERS).json()['id']
    assert next(e for e in a.get('/api/entries').json() if e['id']==legacy)['tags']==[]

def test_full_tag_library_still_reuses_existing_tag(monkeypatch):
    import app.tags as main
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client()
    tag=a.post('/api/tags',json={'name':'容量测试'},headers=HEADERS).json()
    count=len(a.get('/api/tags').json())
    monkeypatch.setattr(main,'MAX_TAGS',count)
    assert a.post('/api/tags',json={'name':'容量测试'},headers=HEADERS).json()==tag
    assert a.post('/api/tags',json={'name':'已超出容量'},headers=HEADERS).status_code==400

def test_anniversaries_private():
    assert TestClient(app).get('/api/anniversaries').status_code == 401
    with db() as c:
        c.execute('DELETE FROM attempts')
    data=client().get('/api/anniversaries').json()
    assert data['together']=='2026-03-21'
    assert data['birthdays']==[{'name':'飞飞','day':'2000-09-22'},{'name':'巧巧','day':'2000-08-25'}]

def test_creation_date_bounds_and_video_local_protocols(monkeypatch):
    from app import media as main
    with db() as c:
        c.execute('DELETE FROM attempts')
    a=client()
    before=len(a.get('/api/entries').json())
    for day in ('1899-12-31','2201-01-01','2026-02-30'):
        assert a.post('/api/entries',data={'day':day,'body':'invalid'},headers=HEADERS).status_code==400
    assert len(a.get('/api/entries').json())==before
    for day in ('1900-01-01','2200-12-31'):
        assert a.post('/api/entries',data={'day':day,'body':'boundary'},headers=HEADERS).status_code==200
    commands=[]
    def fake_run(args,**kwargs):
        commands.append(args)
        class Result: stdout='{"streams":[{"codec_name":"h264"}]}'
        return Result()
    monkeypatch.setattr(main.subprocess,'run',fake_run)
    assert main.validate_video(MEDIA/'test')
    assert main.video_thumb(MEDIA/'test',MEDIA/'thumb')
    for command in commands:
        assert command[command.index('-protocol_whitelist')+1]=='file,pipe'
