"""Tags feature: routes and supporting logic."""
import secrets
import time
import unicodedata
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from .auth import user
from .core import db

router = APIRouter()

MAX_TAGS = 200
MAX_ENTRY_TAGS = 8

def validate_tag_ids(value):
    if not isinstance(value, list) or len(value) > MAX_ENTRY_TAGS or any(not isinstance(t, str) or len(t) != 32 for t in value):
        raise HTTPException(400, '每条记录最多选择 8 个有效标签')
    return list(dict.fromkeys(value))


def check_tags(c, tag_ids):
    for tid in tag_ids:
        if not c.execute('SELECT 1 FROM tags WHERE id=?', (tid,)).fetchone():
            raise HTTPException(400, '所选标签不存在，请重新选择')


@router.get('/api/tags')
def list_tags(request: Request):
    user(request)
    with db() as c:
        return [dict(r) for r in c.execute('SELECT id,name FROM tags ORDER BY created,name_key')]


@router.post('/api/tags')
async def create_tag(request: Request):
    u = user(request)
    try:
        payload = await request.json()
        name = payload.get('name') if isinstance(payload, dict) else None
        if not isinstance(name, str) or len(name) > 200:
            raise ValueError()
        name = ' '.join(unicodedata.normalize('NFKC', name).split())
        if not 1 <= len(name) <= 24 or any(unicodedata.category(ch) == 'Cc' for ch in name):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, '标签名称请填写 1–24 个字')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute('SELECT id,name FROM tags WHERE name_key=?', (name.casefold(),)).fetchone()
        if existing:
            return JSONResponse(dict(existing), status_code=200)
        if c.execute('SELECT count(*) FROM tags').fetchone()[0] >= MAX_TAGS:
            raise HTTPException(400, '共享标签库最多保存 200 个标签，请选择已有标签')
        tag = {'id':secrets.token_hex(16), 'name':name}
        c.execute('INSERT INTO tags VALUES(?,?,?,?,?)', (tag['id'],name,name.casefold(),u['id'],time.time()))
    return JSONResponse(tag, status_code=201)

