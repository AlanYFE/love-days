import io
import os
import json
import zipfile
import subprocess
from pathlib import Path
import pytest
from test_live import photo, video, upload, get_media, reset_login_limit
from test_app import client, HEADERS
from app.main import MEDIA, db
from app.live import unpack_livp

def package(image, movie, name='IMG.jpg'):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr(name,image)
        z.writestr('IMG.mov',movie)
    return result.getvalue()

def test_livp_upload_optout_original_and_delete(video):
    a=client();raw=photo();before=set(MEDIA.iterdir())
    for enabled in (True,False):
        r=upload(a,package(raw,video),enabled=enabled,name='IMG.LIVP')
        assert r.status_code==200,r.text
        m=get_media(a,r.json()['id'])
        assert m['live']==enabled
        assert a.get(m['original_url'] or m['url']).content==raw
        if enabled:
            assert a.get(m['motion_url'],headers={'Range':'bytes=0-99'}).status_code==206
        assert a.delete('/api/entries/'+r.json()['id'],headers=HEADERS).status_code==200
    assert set(MEDIA.iterdir())==before

def test_bad_package_rolls_back(video):
    a=client();before=set(MEDIA.iterdir())
    for raw in (b'broken zip',package(photo(),video,'../escape.jpg'),package(b'not an image',video),package(photo(),b'broken movie')):
        r=upload(a,raw,name='bad.livp')
        assert r.status_code==400,r.text
        assert set(MEDIA.iterdir())==before

def test_archive_expansion_bound(tmp_path):
    source=tmp_path/'large.livp';source.write_bytes(package(b'A'*2048,b'B'*2048))
    with pytest.raises(ValueError,match='超出限制'):
        unpack_livp(source,tmp_path/'photo',tmp_path/'movie',1024,4096)
    with pytest.raises(ValueError,match='超出限制'):
        unpack_livp(source,tmp_path/'photo',tmp_path/'movie',4096,3000)
    assert not (tmp_path/'photo').exists()

@pytest.mark.skipif(not os.getenv('APPLE_LIVE_SAMPLES'),reason='download public Apple samples separately')
@pytest.mark.parametrize('name',['IMG_0011.heic','2023-12-27_12-30-56.jpg'])
def test_public_apple_pair_and_package(name,tmp_path):
    source=Path(os.environ['APPLE_LIVE_SAMPLES'])/name
    image=source.read_bytes();movie=source.with_suffix('.mov').read_bytes()
    a=client()
    for archive in (False,True):
        raw=package(image,movie,name) if archive else image
        r=upload(a,raw,pair=None if archive else movie,name='sample.livp' if archive else name)
        assert r.status_code==200,r.text
        m=get_media(a,r.json()['id']);assert m['live']
        assert a.get(m['original_url']).content==image
        output=tmp_path/'motion.mp4';output.write_bytes(a.get(m['motion_url']).content)
        streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))['streams']
        assert any(s['codec_name']=='h264' for s in streams)
        assert any(s['codec_name']=='aac' for s in streams)
        subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
        assert a.delete('/api/entries/'+r.json()['id'],headers=HEADERS).status_code==200
