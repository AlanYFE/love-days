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
