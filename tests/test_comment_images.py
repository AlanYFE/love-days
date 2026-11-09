import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from app.main import app, db, MEDIA

@pytest.fixture(autouse=True)
def reset_limit():
    with db() as c:c.execute('DELETE FROM attempts')

def picture(fmt='PNG'):
    out=io.BytesIO();Image.new('RGB',(32,48),'green').save(out,fmt);return out.getvalue()

def entry(a):
    return a.post('/api/entries',data={'day':'2026-11-09','body':'image comment test'},headers=HEADERS).json()['id']

def send(a,eid,images,**data):
    return a.post('/api/entries/'+eid+'/comments',data={'body':'','emoji_ids':'[]',**data},files=[('images',(name,raw,'application/octet-stream')) for name,raw in images],headers=HEADERS)

def test_image_only_private_shared_read_and_cleanup():
    a=client();b=client('partner');eid=entry(a);before=set(MEDIA.iterdir())
    r=send(a,eid,[('test.png',picture()),('test.jpg',picture('JPEG'))]);assert r.status_code==201,r.text
    cid=r.json()['id'];images=r.json()['images'];assert len(images)==2
    records=b.get('/api/entries?day=2026-11-09').json()
    comment=next(e for e in records if e['id']==eid)['comments'][0]
    assert comment['images']==images and comment['body']==''
    for image in images:
        for url in (image['url'],image['thumb']):
            assert TestClient(app).get(url).status_code==401
            response=b.get(url);assert response.status_code==200
            assert response.headers['cache-control']=='no-store'
            assert Image.open(io.BytesIO(response.content)).size==(32,48)
    assert b.delete('/api/comments/'+cid,headers=HEADERS).status_code==403
    assert a.delete('/api/comments/'+cid,headers=HEADERS).status_code==200
    assert set(MEDIA.iterdir())==before
    assert b.get(images[0]['url']).status_code==404

def test_heic_gif_and_post_delete():
    a=client();eid=entry(a);before=set(MEDIA.iterdir())
    r=send(a,eid,[('test.heic',picture('HEIF')),('test.gif',picture('GIF'))],body='照片留言')
    assert r.status_code==201,r.text
    images=r.json()['images']
    assert a.get(images[0]['url']).headers['content-type']=='image/jpeg'
    assert a.get(images[1]['url']).headers['content-type']=='image/gif'
    assert a.delete('/api/entries/'+eid,headers=HEADERS).status_code==200
    assert set(MEDIA.iterdir())==before
    with db() as c:assert not c.execute('SELECT 1 FROM comment_media WHERE comment_id=?',(r.json()['id'],)).fetchone()

def test_invalid_files_size_count_and_emoji_rollback(monkeypatch):
    import app.comments as comments
    a=client();eid=entry(a);before=set(MEDIA.iterdir())
    for images,data,status in [
        ([('valid.png',picture()),('fake.jpg',b'<svg></svg>')],{},400),
        ([('x.png',picture())]*5,{},400),
        ([('x.png',picture())],{'emoji_ids':json.dumps(['f'*32])},400),
        ([('x.png',picture())],{'emoji_ids':'broken'},400),
    ]:
        r=send(a,eid,images,**data);assert r.status_code==status,r.text
        assert set(MEDIA.iterdir())==before
    monkeypatch.setattr(comments,'MAX_COMMENT_IMAGE_BYTES',64)
    assert send(a,eid,[('big.png',picture())]).status_code==413
    assert set(MEDIA.iterdir())==before
    with db() as c:assert c.execute('SELECT COUNT(*) FROM comments WHERE entry_id=?',(eid,)).fetchone()[0]==0

def test_deleted_parent_during_processing_rolls_back(monkeypatch):
    import app.comments as comments
    a=client();eid=entry(a);before=set(MEDIA.iterdir());original=comments.prepare_image
    def remove_parent(*args):
        result=original(*args)
        with db() as c:c.execute('DELETE FROM entries WHERE id=?',(eid,))
        return result
    monkeypatch.setattr(comments,'prepare_image',remove_parent)
    r=send(a,eid,[('image.png',picture())]);assert r.status_code==404,r.text
    assert set(MEDIA.iterdir())==before
