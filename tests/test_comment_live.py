import json
import pytest
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from test_live import photo, video, embedded
from test_livp import package
from test_comment_images import entry, reset_limit
from app.main import app, MEDIA, db

def send_live(a,eid,raw,pair=None,name='photo.jpg',enabled=True):
    files=[('images',(name,raw,'application/octet-stream'))]
    if pair is not None:files.append(('live_0',('pair.mov',pair,'video/quicktime')))
    return a.post('/api/entries/'+eid+'/comments',data={'body':'','live_options':json.dumps([{'enabled':enabled,'paired':pair is not None}])},files=files,headers=HEADERS)

@pytest.mark.parametrize('kind',['embedded','paired','livp'])
def test_comment_live_playback_permissions_and_cleanup(kind,video):
    a=client();b=client('partner');eid=entry(a);before=set(MEDIA.iterdir())
    raw=embedded(video) if kind=='embedded' else package(photo(),video) if kind=='livp' else photo()
    r=send_live(a,eid,raw,pair=video if kind=='paired' else None,name='a.livp' if kind=='livp' else 'a.jpg')
    assert r.status_code==201,r.text
    cid=r.json()['id'];image=r.json()['images'][0];assert image['live']
    records=b.get('/api/entries').json();saved=next(e for e in records if e['id']==eid)['comments'][0]['images'][0]
    assert saved==image
    assert TestClient(app).get(image['motion_url']).status_code==401
    response=b.get(image['motion_url'],headers={'Range':'bytes=0-99'})
    assert response.status_code==206 and response.headers['content-type']=='video/mp4'
    assert b.delete('/api/comments/'+cid,headers=HEADERS).status_code==403
    # Both deletion paths must remove original motion and playback derivative.
    path='/api/entries/'+eid if kind=='livp' else '/api/comments/'+cid
    assert a.delete(path,headers=HEADERS).status_code==200
    assert set(MEDIA.iterdir())==before
    assert b.get(image['motion_url']).status_code==404

@pytest.mark.parametrize('livp',[False,True])
def test_comment_live_optout(livp,video):
    a=client();eid=entry(a)
    r=send_live(a,eid,package(photo(),video) if livp else embedded(video),name='a.livp' if livp else 'a.jpg',enabled=False)
    assert r.status_code==201,r.text
    image=r.json()['images'][0];assert not image['live'] and image['motion_url'] is None
    with db() as c:assert c.execute('SELECT COUNT(*) FROM comment_media_extras WHERE media_id=?',(image['id'],)).fetchone()[0]==0

def test_comment_live_missing_invalid_overlong_and_oversize(video,monkeypatch,tmp_path):
    import app.comments as comments
    import subprocess
    a=client();eid=entry(a);before=set(MEDIA.iterdir())
    long=tmp_path/'long.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=32x32:d=16','-c:v','libx264',str(long)],check=True)
    for raw,pair,name in [(photo(),None,'a.jpg'),(photo(),b'broken','a.jpg'),(photo(),long.read_bytes(),'a.jpg'),(b'broken',None,'a.livp')]:
        r=send_live(a,eid,raw,pair,name);assert r.status_code==400,r.text
        assert set(MEDIA.iterdir())==before
    monkeypatch.setattr(comments,'MAX_COMMENT_IMAGE_BYTES',len(photo())+10)
    r=send_live(a,eid,photo(),video);assert r.status_code==413,r.text
    assert set(MEDIA.iterdir())==before
