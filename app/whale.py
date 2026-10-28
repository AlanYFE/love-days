"""Private whale bridge. A service token cannot act as either human member."""
import hmac
import os
import re
import time
from datetime import date
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from .auth import user
from .core import ROOT, db

router = APIRouter()
with db() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS whale_messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT REFERENCES users(id), body TEXT NOT NULL, created REAL NOT NULL,
      reply_to INTEGER UNIQUE REFERENCES whale_messages(id) ON DELETE CASCADE,
      client_id TEXT UNIQUE,
      CHECK ((user_id IS NOT NULL AND reply_to IS NULL) OR
             (user_id IS NULL AND reply_to IS NOT NULL))
    );
    CREATE INDEX IF NOT EXISTS whale_messages_user_created ON whale_messages(user_id,created);
    ''')


def agent(request):
    expected = os.getenv('WHALE_API_TOKEN', '')
    if len(expected) < 32:
        raise HTTPException(503, '小鲸鱼尚未接入')
    value = request.headers.get('authorization', '')
    supplied = value[7:] if value.startswith('Bearer ') else ''
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, '服务凭据无效')


async def payload(request):
    if len(await request.body()) > 16384:
        raise HTTPException(413, '消息太长')
    try:
        p = await request.json()
    except ValueError:
        raise HTTPException(400, '消息格式无效')
    if not isinstance(p, dict):
        raise HTTPException(400, '消息格式无效')
    body = p.get('body')
    if not isinstance(body, str) or not body.strip() or len(body) > 4000:
        raise HTTPException(400, '消息须为 1–4000 字')
    return p, body.strip()


def message_rows(c, where='', args=(), limit=100):
    return [dict(r) for r in c.execute('''
      SELECT m.id,m.user_id,COALESCE(u.name,'小鲸鱼') AS author,
        m.body,m.created,m.reply_to FROM whale_messages m
      LEFT JOIN users u ON u.id=m.user_id
    ''' + where + ' ORDER BY m.id DESC LIMIT ?', (*args, limit))][::-1]


@router.get('/whale')
def page():
    return FileResponse(ROOT / 'static' / 'whale.html', headers={'Cache-Control':'no-store'})


@router.get('/api/whale/messages')
def messages(request: Request):
    user(request)
    with db() as c:
        result = message_rows(c)
    return {'messages':result, 'enabled':len(os.getenv('WHALE_API_TOKEN','')) >= 32}


@router.post('/api/whale/messages', status_code=201)
async def send(request: Request):
    u = user(request)
    if len(os.getenv('WHALE_API_TOKEN','')) < 32:
        raise HTTPException(503, '小鲸鱼尚未接入')
    p, body = await payload(request)
    client_id = p.get('client_id', '')
    if not isinstance(client_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', client_id):
        raise HTTPException(400, '消息编号无效')
    now = time.time()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute('SELECT id,user_id,body FROM whale_messages WHERE client_id=?', (client_id,)).fetchone()
        if old:
            if old['user_id'] != u['id'] or old['body'] != body:
                raise HTTPException(409, '消息编号已使用')
            return {'id':old['id']}
        if c.execute('SELECT COUNT(*) FROM whale_messages WHERE user_id=? AND created>?', (u['id'],now-3600)).fetchone()[0] >= 30:
            raise HTTPException(429, '每人每小时最多 30 条，请稍后再聊')
        pending = c.execute('''SELECT COUNT(*) FROM whale_messages m WHERE m.user_id IS NOT NULL
          AND NOT EXISTS(SELECT 1 FROM whale_messages r WHERE r.reply_to=m.id)''').fetchone()[0]
        if pending >= 20:
            raise HTTPException(429, '小鲸鱼还有消息没回复，请稍后再发')
        mid = c.execute('INSERT INTO whale_messages(user_id,body,created,client_id) VALUES(?,?,?,?)',
                        (u['id'],body,now,client_id)).lastrowid
    return {'id':mid}


@router.get('/api/whale/agent/inbox')
def inbox(request: Request):
    agent(request)
    with db() as c:
        rows = message_rows(c, '''WHERE m.user_id IS NOT NULL AND NOT EXISTS
          (SELECT 1 FROM whale_messages r WHERE r.reply_to=m.id)''', limit=20)
    return {'messages':rows}


@router.get('/api/whale/agent/history')
def history(request: Request):
    agent(request)
    with db() as c:
        return {'messages':message_rows(c, limit=30)}


@router.post('/api/whale/agent/reply/{mid}', status_code=201)
async def reply(mid: int, request: Request):
    agent(request)
    _, body = await payload(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM whale_messages WHERE id=? AND user_id IS NOT NULL',(mid,)).fetchone():
            raise HTTPException(404, '原消息不存在')
        old = c.execute('SELECT id FROM whale_messages WHERE reply_to=?',(mid,)).fetchone()
        if old:
            return {'id':old['id'], 'already_replied':True}
        rid = c.execute('INSERT INTO whale_messages(body,created,reply_to) VALUES(?,?,?)',
                        (body,time.time(),mid)).lastrowid
    return {'id':rid, 'already_replied':False}


@router.get('/api/whale/agent/entries')
def feed(request: Request, day: str | None = None, before: str | None = None, limit: int = 10):
    agent(request)
    if not 1 <= limit <= 20:
        raise HTTPException(400, '每次读取 1–20 条')
    clauses, args = [], []
    if day is not None:
        try:
            d = date.fromisoformat(day)
            if d.isoformat() != day or not 1900 <= d.year <= 2200:
                raise ValueError()
        except ValueError:
            raise HTTPException(400, '日期格式不正确')
        clauses.append('e.day=?'); args.append(day)
    with db() as c:
        c.execute('BEGIN')
        if before:
            cursor = c.execute('SELECT created,id FROM entries WHERE id=?',(before,)).fetchone()
            if not cursor:
                raise HTTPException(400, '分页位置已失效，请重新读取')
            clauses.append('(e.created<? OR (e.created=? AND e.id<?))')
            args.extend((cursor['created'],cursor['created'],cursor['id']))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        rows = [dict(r) for r in c.execute('''SELECT e.id,e.day,e.body,e.created,u.name AS author
          FROM entries e JOIN users u ON u.id=e.user_id''' + where +
          ' ORDER BY e.created DESC,e.id DESC LIMIT ?', (*args,limit+1))]
        more = len(rows) > limit
        rows = rows[:limit]
        for row in rows:
            row['tags'] = [r[0] for r in c.execute('SELECT t.name FROM entry_tags et JOIN tags t ON t.id=et.tag_id WHERE et.entry_id=? ORDER BY t.id',(row['id'],))]
            row['comments'] = [dict(r) for r in c.execute('''SELECT u.name AS author,c.body,c.created
              FROM comments c JOIN users u ON u.id=c.user_id WHERE entry_id=?
              ORDER BY c.created DESC,c.id DESC LIMIT 20''',(row['id'],))][::-1]
            row['media_count'] = c.execute('SELECT COUNT(*) FROM media WHERE entry_id=?',(row['id'],)).fetchone()[0]
    return {'entries':rows,'next_before':rows[-1]['id'] if more else None}
