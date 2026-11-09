"""Entries feature: routes and supporting logic."""
import asyncio
import json
import secrets
import time
from PIL import Image
from datetime import date
from fastapi import APIRouter, HTTPException, Request
from .activities import add_activity
from .auth import user
from .core import LIVE_PROCESSING, MAX_FILE, MAX_TOTAL, MEDIA, db
from .live import extract_motion, motion_range, still_jpeg, transcode_motion, unpack_livp
from .locations import save_location, stored_location, validate_location
from .media import make_image, validate_video, video_thumb
from .tags import check_tags, validate_tag_ids

router = APIRouter()

@router.post('/api/entries')
async def create(request: Request):
    u = user(request)  # Authenticate before parsing large multipart bodies.
    paths = []
    try:
        async with request.form(max_files=24, max_fields=5, max_part_size=64*1024) as form:
            day = form.get('day','')
            body = form.get('body','')
            try:
                if (not isinstance(day,str) or not isinstance(body,str) or len(body)>5000
                    or date.fromisoformat(day).isoformat()!=day or not 1900<=date.fromisoformat(day).year<=2200):
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400,'日期无效，或文字超过 5000 字')
            try:
                tag_ids = validate_tag_ids(json.loads(form.get('tag_ids', '[]')))
            except (ValueError, TypeError):
                raise HTTPException(400, '标签格式无效')
            with db() as c:
                check_tags(c, tag_ids)
            try:
                location=validate_location(json.loads(form.get('location','null')))
            except (ValueError,TypeError):
                raise HTTPException(400,'地点格式无效')
            files = form.getlist('files')
            if len(files) > 12:
                raise HTTPException(400, '每条记录最多 12 个附件')
            try:
                options = json.loads(form.get('live_options', 'null'))
                if options is not None and (not isinstance(options, list) or len(options) != len(files) or any(not isinstance(o, dict) or type(o.get('enabled')) is not bool or type(o.get('paired')) is not bool for o in options)):
                    raise ValueError()
                for key,value in form.multi_items():
                    if hasattr(value, 'read') and key != 'files' and (options is None or key not in {f'live_{i}' for i,o in enumerate(options) if o['enabled'] and o['paired']}):
                        raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400, '实况选项无效，请重新选择附件')
            if not body.strip() and not files:
                raise HTTPException(400, '请写点文字或添加照片／视频')
            eid = secrets.token_hex(16)
            rows, extra_rows, total = [], [], 0
            for index, f in enumerate(files):
                if not hasattr(f, 'read'):
                    raise HTTPException(400,'附件无效')
                mid = secrets.token_hex(16)
                path = MEDIA / mid
                paths.append(path)
                size = 0
                with path.open('wb') as out:
                    while chunk := await f.read(1024*1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size>MAX_FILE or total>MAX_TOTAL:
                            raise HTTPException(413, '单文件上限 100 MB，每次合计 200 MB')
                        out.write(chunk)
                thumb = MEDIA / (mid+'.jpg')
                paths.append(thumb)
                display = motion = companion = None
                choice = options[index] if options is not None else {'enabled':True,'paired':False}
                package = (f.filename or '').lower().endswith('.livp')
                if package:
                    if choice['paired']:
                        raise HTTPException(400, '实况包已包含视频，无需补选')
                    unpacked = MEDIA / (mid+'.unpacked')
                    companion = MEDIA / (mid+'.source.mov')
                    paths.extend((unpacked, companion))
                    try:
                        unpacked_size = await asyncio.to_thread(unpack_livp,path,unpacked,companion,MAX_FILE,MAX_TOTAL-total+size)
                        total += max(0, unpacked_size-size)
                        unpacked.replace(path)
                        if not choice['enabled']:
                            companion.unlink()
                            companion = None
                    except ValueError as exc:
                        raise HTTPException(400, str(exc))
                try:
                    await asyncio.to_thread(make_image,path,thumb)
                    with Image.open(path) as original:
                        kind, mime = 'image', Image.MIME.get(original.format, 'image/jpeg')
                        heif = original.format in ('HEIF', 'AVIF')
                except Exception:
                    if package:
                        raise HTTPException(400, '实况包中的照片无法读取')
                    with path.open('rb') as stream:
                        head = stream.read(32)
                    if head[4:8] != b'ftyp' or head[8:12] in (b'heic',b'heix',b'mif1',b'avif') or not await asyncio.to_thread(validate_video,path):
                        raise HTTPException(400,'图片或视频无法读取，请使用 JPG、PNG、WebP、HEIC 或 MP4／MOV')
                    kind, mime = 'video', 'video/mp4'
                    await asyncio.to_thread(video_thumb,path,thumb)
                if kind == 'image':
                    try:
                        # A damaged live file can still be explicitly saved as a still.
                        span = await asyncio.to_thread(motion_range,path) if choice['enabled'] else None
                        if choice['paired'] and choice['enabled']:
                            fpair = form.get('live_'+str(index))
                            if not hasattr(fpair, 'read'):
                                raise ValueError('请补选实况对应的视频')
                            companion = MEDIA / (mid+'.source.mov')
                            paths.append(companion)
                            pair_size = 0
                            with companion.open('wb') as out:
                                while chunk := await fpair.read(1024*1024):
                                    pair_size += len(chunk)
                                    total += len(chunk)
                                    if pair_size > MAX_FILE or total > MAX_TOTAL:
                                        raise HTTPException(413, '配套视频计入上传限制：单个 100 MB，合计 200 MB')
                                    out.write(chunk)
                        elif companion:
                            pass  # Already unpacked from a .livp package.
                        elif span:
                            companion = MEDIA / (mid+'.source.mov')
                            paths.append(companion)
                            await asyncio.to_thread(extract_motion,path,companion,span)
                        elif options is not None and choice['enabled']:
                            raise ValueError('没有收到实况视频，请从文件中选择原图、补选配套视频，或取消保留实况')
                        if companion:
                            motion = MEDIA / (mid+'.live.mp4')
                            paths.append(motion)
                            async with LIVE_PROCESSING:
                                await asyncio.to_thread(transcode_motion,companion,motion)
                        if heif or motion:
                            display = MEDIA / (mid+'.display.jpg')
                            paths.append(display)
                            await asyncio.to_thread(still_jpeg,path,display)
                        elif not choice['enabled']:
                            # Strip embedded motion when the user chooses "still only".
                            with path.open('rb') as stream:
                                head = stream.read(1024*1024)
                            if b'MotionPhoto' in head or b'MicroVideo' in head:
                                display = MEDIA / (mid+'.display.jpg')
                                paths.append(display)
                                await asyncio.to_thread(still_jpeg,path,display)
                                display.replace(path)
                                display = None
                                mime = 'image/jpeg'
                    except ValueError as exc:
                        raise HTTPException(400, str(exc))
                    if display or motion or companion:
                        extra_rows.append((mid,display.name if display else None,motion.name if motion else None,companion.name if companion else None))
                elif options is not None and (choice['enabled'] or choice['paired']):
                    raise HTTPException(400, '实况选项只适用于照片')
                rows.append((mid,eid,kind,mime,mid,thumb.name if thumb.exists() else None))
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                check_tags(c, tag_ids)
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(eid,u['id'],day,body.strip(),time.time()))
                add_activity(c,u['id'],'post',eid,body.strip() or '发布了照片或视频')
                save_location(c,eid,location)
                c.executemany('INSERT INTO media VALUES(?,?,?,?,?,?)',rows)
                c.executemany('INSERT INTO media_extras VALUES(?,?,?,?)',extra_rows)
                c.executemany('INSERT INTO entry_tags VALUES(?,?)', [(eid,tid) for tid in tag_ids])
        return {'id':eid}
    except BaseException:
        for p in paths:
            p.unlink(missing_ok=True)
        raise


@router.patch('/api/entries/{eid}')
async def edit_entry(eid: str, request: Request):
    u = user(request)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError()
        day, body = payload.get('day'), payload.get('body')
        if not isinstance(day, str) or not isinstance(body, str) or len(body) > 5000:
            raise ValueError()
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day or not 1900 <= parsed.year <= 2200:
            raise ValueError()
        original = payload.get('original')
        if not isinstance(original, dict) or not all(isinstance(original.get(k), str) for k in ('day', 'body')):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, '编辑内容无效：请检查日期和文字（最多 5000 字）')
    tag_ids = validate_tag_ids(payload['tag_ids']) if 'tag_ids' in payload else None
    original_tags = validate_tag_ids(original.get('tag_ids')) if tag_ids is not None else None
    change_location = 'location' in payload
    location = validate_location(payload['location']) if change_location else None
    if change_location and 'location' not in original:
        raise HTTPException(400,'缺少原始地点，请刷新后重试')
    original_location=validate_location(original['location']) if change_location else None
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        entry = c.execute('SELECT * FROM entries WHERE id=?', (eid,)).fetchone()
        if not entry:
            raise HTTPException(404, '帖子已删除或不存在')
        if entry['user_id'] != u['id']:
            raise HTTPException(403, '只能编辑自己发布的记录')
        if any(entry[k] != original[k] for k in ('day', 'body')):
            raise HTTPException(409, '这条记录已在其他页面修改，请保留草稿，关闭并刷新后重新编辑')
        if change_location and stored_location(c,eid)!=original_location:
            raise HTTPException(409,'地点已在其他页面修改，请保留草稿，关闭并刷新后重新编辑')
        if tag_ids is not None:
            current_tags = {r['tag_id'] for r in c.execute('SELECT tag_id FROM entry_tags WHERE entry_id=?', (eid,))}
            if current_tags != set(original_tags):
                raise HTTPException(409, '标签已在其他页面修改，请保留草稿，关闭并刷新后重新编辑')
            check_tags(c, tag_ids)
        if not body.strip() and not c.execute('SELECT 1 FROM media WHERE entry_id=?', (eid,)).fetchone():
            raise HTTPException(400, '没有附件的记录不能清空文字')
        if change_location:
            save_location(c,eid,location)
        c.execute('UPDATE entries SET day=?,body=? WHERE id=?', (day, body.strip(), eid))
        if tag_ids is not None:
            c.execute('DELETE FROM entry_tags WHERE entry_id=?', (eid,))
            c.executemany('INSERT INTO entry_tags VALUES(?,?)', [(eid,tid) for tid in tag_ids])
    return {'ok': True, 'id': eid, 'day': day}


@router.delete('/api/entries/{eid}')
def delete(eid: str, request: Request):
    u = user(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        e = c.execute('SELECT user_id FROM entries WHERE id=?',(eid,)).fetchone()
        if not e:
            raise HTTPException(404,'记录不存在')
        if e['user_id']!=u['id']:
            raise HTTPException(403,'只能删除自己发布的记录')
        rows = c.execute('SELECT path,thumb FROM media WHERE entry_id=?',(eid,)).fetchall()
        rows += c.execute('SELECT x.display,x.motion,x.companion FROM media_extras x JOIN media m ON m.id=x.media_id WHERE m.entry_id=?',(eid,)).fetchall()
        rows += c.execute('SELECT path,thumb,display FROM comment_media WHERE comment_id IN (SELECT id FROM comments WHERE entry_id=?)',(eid,)).fetchall()
        c.execute('DELETE FROM entries WHERE id=?',(eid,))
    for row in rows:
        for name in row:
            if name:
                (MEDIA / name).unlink(missing_ok=True)
    return {'ok':True}

