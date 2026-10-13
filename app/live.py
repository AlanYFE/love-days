"""Bounded Motion Photo extraction and a browser-compatible playback derivative."""
import json
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
CAM = 'http://ns.google.com/photos/1.0/camera/'
ITEM = 'http://ns.google.com/photos/1.0/container/item/'
OP = 'http://ns.oplus.com/photos/1.0/camera/'

def motion_range(path):
    # Read XMP from the still image, not by searching arbitrary video bytes.
    with Image.open(path) as im:
        raw = im.info.get('xmp', b'')
    if not raw:
        return None
    if isinstance(raw, str):
        raw = raw.encode()
    if len(raw) > 1024 * 1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('实况元数据无效')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    attrs = {key:value for node in root.iter() for key,value in node.attrib.items()}
    if attrs.get('{'+CAM+'}MotionPhoto') != '1':
        return None
    items = [node for node in root.iter() if '{'+ITEM+'}Semantic' in node.attrib]
    size = path.stat().st_size
    remaining = 0
    for node in reversed(items):
        semantic = node.get('{'+ITEM+'}Semantic')
        if semantic == 'Primary':
            break
        length = int(node.get('{'+ITEM+'}Length', '0'))
        padding = int(node.get('{'+ITEM+'}Padding', '0'))
        if length < 0 or padding < 0 or length + padding + remaining > size:
            raise ValueError('实况文件不完整')
        if semantic == 'MotionPhoto' and node.get('{'+ITEM+'}Mime') == 'video/mp4':
            offset = size - remaining - padding - length
            # OPlus v2 can append an additional effect stream after its primary movie.
            primary = int(attrs.get('{'+OP+'}VideoLength', str(length)))
            if not 16 <= primary <= length or offset < 2:
                raise ValueError('实况视频长度无效')
            with path.open('rb') as f:
                f.seek(offset)
                header = f.read(12)
            if header[4:8] != b'ftyp':
                raise ValueError('实况视频缺失，请使用原始文件')
            return offset, primary
        remaining += length + padding
    raise ValueError('发现实况标记，但未找到可读取的视频')

def extract_motion(source, target, span):
    offset, length = span
    with source.open('rb') as inp, target.open('wb') as out:
        inp.seek(offset)
        while length:
            chunk = inp.read(min(length, 1024*1024))
            if not chunk:
                raise ValueError('实况视频不完整')
            out.write(chunk)
            length -= len(chunk)

def still_jpeg(source, target):
    with Image.open(source) as im:
        ImageOps.exif_transpose(im).convert('RGB').save(target, 'JPEG', quality=94)

def transcode_motion(source, target):
    try:
        probe = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(source)],check=True,capture_output=True,timeout=15)
        data = json.loads(probe.stdout)
        video = next(s for s in data['streams'] if s['codec_type']=='video')
        duration = float(data['format']['duration'])
        if not 0 < duration <= 15 or not 0 < video['width']*video['height'] <= 40_000_000:
            raise ValueError()
        subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','2','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:v:0','-map','0:a:0?','-map_metadata','-1','-vf',"scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",'-c:v','libx264','-threads','2','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart','-t','15','-f','mp4','-y',str(target)],check=True,capture_output=True,timeout=90)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration):
        target.unlink(missing_ok=True)
        raise ValueError('实况视频处理失败，请使用完整的配套 MOV/MP4（最长 15 秒），或取消保留实况后重试')
