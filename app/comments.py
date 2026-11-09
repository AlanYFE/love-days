"""Comments with private, bounded image attachments."""
import asyncio
import json
import secrets
import time
from contextlib import AsyncExitStack
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, HTTPException, Request
from .activities import add_activity
from .auth import user
from .core import db, MEDIA, LIVE_PROCESSING
from .media import make_image
from .live import still_jpeg, motion_range, extract_motion, transcode_motion, unpack_livp

router = APIRouter()
MAX_COMMENT_IMAGES = 4
MAX_COMMENT_IMAGE_BYTES = 10 * 1024 * 1024


def prepare_image(source, thumb, display):
    try:
        with Image.open(source) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP', 'GIF', 'HEIF'):
                raise ValueError()
            mime = Image.MIME.get(im.format, 'image/jpeg')
            heif = im.format == 'HEIF'
            im.verify()
        make_image(source, thumb)
        if heif:
            still_jpeg(source, display)
        return mime, display.name if heif else None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, '评论图片无法读取，请使用 JPG、PNG、WebP、GIF 或 HEIC 图片')


@router.post('/api/entries/{eid}/comments', status_code=201)
async def add_comment(eid: str, request: Request):
    u = user(request)
    paths, rows, extras = [], [], []
    committed = False
    try:
        async with AsyncExitStack() as stack:
            files = []
            options = None
            if request.headers.get('content-type', '').split(';')[0].strip().lower() == 'multipart/form-data':
                form = await stack.enter_async_context(request.form(max_files=MAX_COMMENT_IMAGES*2, max_fields=3, max_part_size=16*1024))
                try:
                    payload = {'body': form.get('body', ''), 'emoji_ids': json.loads(form.get('emoji_ids', '[]'))}
                except (ValueError, TypeError):
                    raise HTTPException(400, '评论格式无效')
                files = form.getlist('images')
                try:
                    options = json.loads(form.get('live_options','null'))
                    if options is not None and (not isinstance(options,list) or len(options)!=len(files) or any(not isinstance(o,dict) or type(o.get('enabled')) is not bool or type(o.get('paired')) is not bool or (o['paired'] and not o['enabled']) for o in options)):
                        raise ValueError()
                    allowed = {f'live_{i}' for i,o in enumerate(options or []) if o['paired']}
                    if any(hasattr(value,'read') and key!='images' and key not in allowed for key,value in form.multi_items()):
                        raise ValueError()
                except (ValueError,TypeError):
                    raise HTTPException(400,'评论实况选项无效，请重新选择附件')
            else:
                try:
                    payload = await request.json()
                except ValueError:
                    raise HTTPException(400, '评论格式无效')
            body = payload.get('body') if isinstance(payload, dict) else None
            emoji_ids = payload.get('emoji_ids', []) if isinstance(payload, dict) else []
            if (not isinstance(body, str) or len(body) > 1000 or not isinstance(emoji_ids, list)
                    or len(emoji_ids) > 8 or any(not isinstance(e, str) or len(e) != 32 for e in emoji_ids)
                    or len(files) > MAX_COMMENT_IMAGES or any(not hasattr(f, 'read') for f in files)
                    or (not body.strip() and not emoji_ids and not files)):
                raise HTTPException(400, '请输入评论、选择表情或添加图片；最多 1000 字、8 个表情和 4 张图片')
            with db() as c:
                if not c.execute('SELECT 1 FROM entries WHERE id=?', (eid,)).fetchone():
                    raise HTTPException(404, '帖子已删除或不存在')
            comment = {'id': secrets.token_hex(16), 'entry_id': eid, 'user_id': u['id'],
                       'author': u['name'], 'body': body.strip(), 'created': time.time()}
            for position, f in enumerate(files):
                choice = options[position] if options is not None else {'enabled':True,'paired':False}
                mid = secrets.token_hex(16)
                path, thumb, display = (MEDIA / (mid+suffix) for suffix in ('', '.jpg', '.display.jpg'))
                paths.extend((path, thumb, display))
                size = 0
                with path.open('wb') as out:
                    while chunk := await f.read(1024*1024):
                        size += len(chunk)
                        if size > MAX_COMMENT_IMAGE_BYTES:
                            raise HTTPException(413, '每张评论图片不能超过 10 MB')
                        out.write(chunk)
                companion, motion = MEDIA/(mid+'.source.mov'), MEDIA/(mid+'.live.mp4')
                paths.extend((companion,motion))
                package = (f.filename or '').lower().endswith('.livp')
                try:
                    if package:
                        if choice['paired']:
                            raise ValueError('实况包已包含视频，无需补选')
                        unpacked = MEDIA/(mid+'.unpacked');paths.append(unpacked)
                        await asyncio.to_thread(unpack_livp,path,unpacked,companion,MAX_COMMENT_IMAGE_BYTES,MAX_COMMENT_IMAGE_BYTES)
                        unpacked.replace(path)
                        if not choice['enabled']:
                            companion.unlink()
                    mime, display_name = await asyncio.to_thread(prepare_image, path, thumb, display)
                    span = await asyncio.to_thread(motion_range,path) if choice['enabled'] else None
                    if choice['paired']:
                        pair = form.get('live_'+str(position))
                        if not hasattr(pair,'read'):
                            raise ValueError('请补选实况对应的视频')
                        with companion.open('wb') as out:
                            while chunk := await pair.read(1024*1024):
                                size += len(chunk)
                                if size > MAX_COMMENT_IMAGE_BYTES:
                                    raise HTTPException(413,'每张评论实况的照片与视频合计不能超过 10 MB')
                                out.write(chunk)
                    elif choice['enabled'] and not companion.exists() and span:
                        await asyncio.to_thread(extract_motion,path,companion,span)
                    elif options is not None and choice['enabled'] and not companion.exists():
                        raise ValueError('没有收到实况视频，请补选配套视频或取消保留实况')
                    if companion.exists():
                        async with LIVE_PROCESSING:
                            await asyncio.to_thread(transcode_motion,companion,motion)
                        extras.append((mid,motion.name,companion.name))
                        await asyncio.to_thread(still_jpeg,path,display)
                        display_name = display.name
                except ValueError as exc:
                    raise HTTPException(400,str(exc))
                rows.append((mid, comment['id'], position, mime, path.name, thumb.name, display_name))
            with db() as c:
                # Recheck after uploads to serialize against parent deletion.
                c.execute('BEGIN IMMEDIATE')
                if not c.execute('SELECT 1 FROM entries WHERE id=?', (eid,)).fetchone():
                    raise HTTPException(404, '帖子已删除或不存在')
                for emoji_id in emoji_ids:
                    if not c.execute('SELECT 1 FROM emojis WHERE id=?', (emoji_id,)).fetchone():
                        raise HTTPException(400, '所选表情不存在，请刷新表情库')
                c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',
                          (comment['id'], eid, u['id'], comment['body'], comment['created']))
                c.executemany('INSERT INTO comment_emojis VALUES(?,?,?)', [(comment['id'], i, e) for i,e in enumerate(emoji_ids)])
                c.executemany('INSERT INTO comment_media VALUES(?,?,?,?,?,?,?)', rows)
                c.executemany('INSERT INTO comment_media_extras VALUES(?,?,?)', extras)
                add_activity(c,u['id'],'comment',eid,comment['body'] or ('发送了图片留言' if rows else '发送了表情留言'),comment['id'])
            committed = True
            live_ids = {r[0] for r in extras}
            comment['images'] = [{'id':r[0],'kind':'image','url':'/comment-media/'+r[0],'thumb':'/comment-media/'+r[0]+'/thumb','live':r[0] in live_ids,'motion_url':'/comment-media/'+r[0]+'/motion' if r[0] in live_ids else None} for r in rows]
            return comment
    finally:
        if not committed:
            for path in paths:
                path.unlink(missing_ok=True)


@router.delete('/api/comments/{cid}')
def delete_comment(cid: str, request: Request):
    u = user(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        comment = c.execute('SELECT user_id FROM comments WHERE id=?', (cid,)).fetchone()
        if not comment:
            raise HTTPException(404, '评论已删除或不存在')
        if comment['user_id'] != u['id']:
            raise HTTPException(403, '只能删除自己的评论')
        rows = c.execute('SELECT path,thumb,display FROM comment_media WHERE comment_id=?', (cid,)).fetchall()
        rows += c.execute('SELECT x.motion,x.companion FROM comment_media_extras x JOIN comment_media m ON m.id=x.media_id WHERE m.comment_id=?',(cid,)).fetchall()
        c.execute('DELETE FROM comments WHERE id=? AND user_id=?', (cid, u['id']))
    for row in rows:
        for name in row:
            if name:
                (MEDIA/name).unlink(missing_ok=True)
    return {'ok': True}
