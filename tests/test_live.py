import io
import json
import os
import subprocess
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from test_app import client, HEADERS
from app.main import app, db, MEDIA
from app.live import motion_range

@pytest.fixture(autouse=True)
def reset_login_limit():
    with db() as c:
        c.execute('DELETE FROM attempts')

@pytest.fixture
def video(tmp_path):
    path=tmp_path/'short.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    return path.read_bytes()

def photo():
    b=io.BytesIO();Image.new('RGB',(32,48),'red').save(b,'JPEG');return b.getvalue()

def embedded(video):
    xmp=(f'<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:c="http://ns.google.com/photos/1.0/camera/" xmlns:i="http://ns.google.com/photos/1.0/container/item/"><node c:MotionPhoto="1"/><item i:Semantic="Primary"/><item i:Semantic="MotionPhoto" i:Mime="video/mp4" i:Length="{len(video)}"/></x:xmpmeta>').encode()
    data=b'http://ns.adobe.com/xap/1.0/\x00'+xmp
    jpg=photo()
    return jpg[:2]+b'\xff\xe1'+(len(data)+2).to_bytes(2,'big')+data+jpg[2:]+video

def upload(a,raw,enabled=True,pair=None,name='photo.jpg'):
    files=[('files',(name,raw,'image/jpeg'))]
    if pair is not None:files.append(('live_0',('pair.mov',pair,'video/quicktime')))
    return a.post('/api/entries',data={'day':'2026-10-13','body':'实况','live_options':json.dumps([{'enabled':enabled,'paired':pair is not None}])},files=files,headers=HEADERS)

def get_media(a,eid):
    return next(e for e in a.get('/api/entries').json() if e['id']==eid)['media'][0]

def test_embedded_live_private_playback_still_optout_and_delete(video):
    a=client();b=client('partner');anon=TestClient(app)
    raw=embedded(video)
    r=upload(a,raw);assert r.status_code==200,r.text
    mid=get_media(a,r.json()['id'])
    assert mid['live'] and mid['kind']=='image'
    assert b.get(mid['url']).headers['content-type']=='image/jpeg'
    assert b.get(mid['original_url']).content==raw
    for path in (mid['motion_url'],mid['original_url']):
        assert anon.get(path).status_code==401
    assert b.get(mid['motion_url'],headers={'Range':'bytes=0-99'}).status_code==206
    r2=upload(a,raw,False);assert r2.status_code==200,r2.text
    still=get_media(a,r2.json()['id'])
    assert not still['live'] and still['motion_url'] is None
    assert b'ftyp' not in a.get(still['url']).content
    with db() as c:
        row=c.execute('SELECT * FROM media_extras WHERE media_id=?',(mid['id'],)).fetchone()
        paths=[MEDIA/row[k] for k in ('display','motion','companion')]
    assert a.delete('/api/entries/'+r.json()['id'],headers=HEADERS).status_code==200
    assert all(not p.exists() for p in paths)
    assert b.get(mid['motion_url']).status_code==404

def test_manual_pair_and_invalid_motion_rollback(video):
    a=client()
    r=upload(a,photo(),pair=video);assert r.status_code==200,r.text
    assert get_media(a,r.json()['id'])['live']
    before=set(MEDIA.iterdir())
    for raw,pair in ((photo(),None),(photo(),b'not a video'),(embedded(b'not a valid mp4'),None)):
        r=upload(a,raw,pair=pair);assert r.status_code==400,r.text
    assert set(MEDIA.iterdir())==before

def test_heic_still_and_paired_upload(video):
    import pillow_heif
    raw=io.BytesIO();Image.new('RGB',(32,48),'green').save(raw,'HEIF')
    a=client()
    for pair in (None,video):
        r=upload(a,raw.getvalue(),enabled=pair is not None,pair=pair,name='test.heic')
        assert r.status_code==200,r.text
        media=get_media(a,r.json()['id'])
        assert media['live']==(pair is not None)
        response=a.get(media['url'])
        assert response.headers['content-type']=='image/jpeg'
        assert Image.open(io.BytesIO(response.content)).size==(32,48)
        assert a.get(media['original_url']).content==raw.getvalue()

@pytest.mark.skipif(not os.getenv('LIVE_SAMPLE'),reason='private device sample supplied separately')
def test_real_oppo_sample():
    source=Path(os.environ['LIVE_SAMPLE'])
    span=motion_range(source)
    assert span and span[1]>1000
    a=client();r=upload(a,source.read_bytes());assert r.status_code==200,r.text
    media=get_media(a,r.json()['id']);assert media['live']
    assert a.get(media['original_url']).content==source.read_bytes()
    response=a.get(media['motion_url']);assert response.status_code==200
    temp=source.parent/'live-output-test.mp4';temp.write_bytes(response.content)
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(temp)]))
    assert any(s['codec_name']=='h264' for s in data['streams'])
    assert any(s['codec_name']=='aac' for s in data['streams'])
    subprocess.run(['ffmpeg','-v','error','-i',str(temp),'-f','null','-'],check=True)
    temp.unlink()
