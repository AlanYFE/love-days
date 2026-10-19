"""Emojis feature: routes and supporting logic."""
import asyncio
import secrets
import time
from PIL import Image
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from .auth import user
from .core import EMOJI_DIR, MAX_EMOJI_BYTES, db

router = APIRouter()

def emoji_data(row):
    result = dict(row)
    result['url'] = '/api/emojis/' + result['id'] + '/image'
    return result


def reaction_map(c, table, scope=None):
    # table is an internal constant, never a user-supplied SQL identifier.
    groups = {}
    where = f' WHERE r.target_id IN ({scope})' if scope else ''
    for row in c.execute(f'SELECT r.target_id,r.user_id,e.id,e.name FROM {table} r JOIN emojis e ON e.id=r.emoji_id{where} ORDER BY e.created,e.id,r.user_id'):
        group = groups.setdefault(row['target_id'], {})
        reaction = group.setdefault(row['id'], {'emoji':emoji_data({'id':row['id'],'name':row['name']}),'user_ids':[],'count':0})
        reaction['user_ids'].append(row['user_id'])
        reaction['count'] += 1
    return {key:list(value.values()) for key,value in groups.items()}


def validate_emoji(path):
    try:
        with Image.open(path) as im:
            if im.format not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
                raise ValueError('format')
            mime = Image.MIME[im.format]
            frames = getattr(im, 'n_frames', 1)
            if max(im.size) > 2048 or frames > 200 or im.width * im.height * frames > 80_000_000:
                raise ValueError('dimensions')
            for index in range(frames):
                im.seek(index)
                im.load()
            return mime
    except Exception:
        raise HTTPException(400, '请使用有效的 JPG、PNG、WebP 或 GIF；最长边 2048 像素，动画最多 200 帧，总像素不超过 8000 万')


@router.get('/api/emojis')
def list_emojis(request: Request):
    user(request)
    with db() as c:
        return [emoji_data(row) for row in c.execute('SELECT id,name,user_id,created FROM emojis ORDER BY created DESC,id')]


@router.post('/api/emojis', status_code=201)
async def upload_emoji(request: Request):
    u = user(request)
    path = None
    try:
        async with request.form(max_files=1, max_fields=1, max_part_size=4096) as form:
            file = form.get('file')
            name = form.get('name', '')
            if not hasattr(file, 'read') or not isinstance(name, str) or not 1 <= len(name.strip()) <= 24:
                raise HTTPException(400, '请选择图片，并填写 1–24 字的表情名称')
            eid = secrets.token_hex(16)
            path = EMOJI_DIR / eid
            size = 0
            with path.open('wb') as out:
                while chunk := await file.read(256 * 1024):
                    size += len(chunk)
                    if size > MAX_EMOJI_BYTES:
                        raise HTTPException(413, '表情图片不能超过 5 MB')
                    out.write(chunk)
            mime = await asyncio.to_thread(validate_emoji, path)
            created = time.time()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT count(*) FROM emojis').fetchone()[0] >= 100:
                    raise HTTPException(400, '共享表情库最多保存 100 个表情')
                c.execute('INSERT INTO emojis VALUES(?,?,?,?,?)', (eid,name.strip(),u['id'],mime,created))
        return emoji_data({'id':eid,'name':name.strip(),'user_id':u['id'],'created':created})
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        raise


@router.get('/api/emojis/{eid}/image')
def emoji_image(eid: str, request: Request):
    user(request)
    with db() as c:
        row = c.execute('SELECT id,mime FROM emojis WHERE id=?', (eid,)).fetchone()
    if not row or not (EMOJI_DIR / row['id']).is_file():
        raise HTTPException(404, '表情不存在')
    return FileResponse(EMOJI_DIR / row['id'], media_type=row['mime'])


@router.put('/api/{kind}/{target_id}/reactions/{emoji_id}')
async def set_reaction(kind: str, target_id: str, emoji_id: str, request: Request):
    u = user(request)
    tables = {'entries':('entries','entry_reactions'), 'comments':('comments','comment_reactions')}
    if kind not in tables:
        raise HTTPException(404)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '回应格式无效')
    if not isinstance(payload, dict) or type(payload.get('active')) is not bool:
        raise HTTPException(400, '请指定是否选中表情')
    parent, table = tables[kind]
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute(f'SELECT 1 FROM {parent} WHERE id=?', (target_id,)).fetchone():
            raise HTTPException(404, '帖子或评论已删除')
        if not c.execute('SELECT 1 FROM emojis WHERE id=?', (emoji_id,)).fetchone():
            raise HTTPException(404, '表情不存在')
        if payload['active']:
            c.execute(f'INSERT OR IGNORE INTO {table} VALUES(?,?,?)', (target_id,emoji_id,u['id']))
        else:
            c.execute(f'DELETE FROM {table} WHERE target_id=? AND emoji_id=? AND user_id=?', (target_id,emoji_id,u['id']))
    return {'ok':True}

