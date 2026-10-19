"""Media feature: routes and supporting logic."""
import json
import subprocess
from PIL import Image, ImageOps
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from .auth import user
from .core import MEDIA, db

router = APIRouter()

def make_image(source, dest):
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((640,640))
        im.convert('RGB').save(dest, 'JPEG', quality=82)


def validate_video(source):
    try:
        result = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-select_streams','v:0','-show_entries','stream=codec_name','-of','json',str(source)], check=True, capture_output=True, timeout=15)
        streams = json.loads(result.stdout).get('streams', [])
        return bool(streams and streams[0].get('codec_name') in ('h264', 'hevc', 'mpeg4', 'av1', 'vp9'))
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def video_thumb(source, dest):
    try:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1','-vf','scale=640:-2','-y',str(dest)], check=True, capture_output=True, timeout=25)
        return True
    except (OSError, subprocess.SubprocessError):
        dest.unlink(missing_ok=True)
        return False


@router.get('/media/{mid}')
@router.get('/media/{mid}/thumb')
@router.get('/media/{mid}/motion')
@router.get('/media/{mid}/original')
def media(mid: str, request: Request):
    user(request)
    with db() as c:
        m = c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
        extra = c.execute('SELECT * FROM media_extras WHERE media_id=?',(mid,)).fetchone()
    if not m:
        raise HTTPException(404)
    suffix = request.url.path.rsplit('/',1)[-1]
    name, mime = m['path'], m['mime']
    if suffix == 'thumb':
        name, mime = m['thumb'], 'image/jpeg'
    elif suffix == 'motion':
        name, mime = extra['motion'] if extra else None, 'video/mp4'
    elif suffix != 'original' and extra and extra['display']:
        name, mime = extra['display'], 'image/jpeg'
    if not name or not (MEDIA/name).is_file():
        raise HTTPException(404)
    return FileResponse(MEDIA/name, media_type=mime)

