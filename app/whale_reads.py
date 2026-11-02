"""User-invited readings. Only the holder of the active lease can finish a post."""
import base64
import os
import secrets
import time
from datetime import date
from fastapi import APIRouter, HTTPException, Request
from .auth import user
from .core import MEDIA, db
from .whale import agent, payload

router = APIRouter()


@router.post('/api/whale/read-day/{day}')
def invite(day: date, request: Request):
    user(request)
    if not 1900 <= day.year <= 2200:
        raise HTTPException(400, '日期超出范围')
    if len(os.getenv('WHALE_API_TOKEN', '')) < 32:
        raise HTTPException(503, '小铃尚未接入')
    day = day.isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("""INSERT INTO whale_reads(entry_id,day,state)
            SELECT id,day,'queued' FROM entries WHERE day=?
            ON CONFLICT(entry_id) DO UPDATE SET state='queued',day=excluded.day,
            ticket=NULL,expires=NULL WHERE whale_reads.reply IS NULL AND
            (whale_reads.state='failed' OR whale_reads.expires<? OR whale_reads.day!=excluded.day)
            """, (day, time.time()))
        return {'queued': c.execute('SELECT changes()').fetchone()[0]}


@router.post('/api/whale/agent/reads/claim')
def claim(request: Request):
    agent(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM whale_reads WHERE state='reading' AND expires>=? LIMIT 1",
                     (time.time(),)).fetchone():
            return {'job': None}
        row = c.execute("""SELECT e.id,e.day,e.body,u.name AS author FROM whale_reads w
            JOIN entries e ON e.id=w.entry_id AND e.day=w.day JOIN users u ON u.id=e.user_id
            WHERE w.state='queued' ORDER BY w.rowid LIMIT 1""").fetchone()
        if row is None:
            return {'job': None}
        job = dict(row)
        ticket = secrets.token_urlsafe(24)
        c.execute("UPDATE whale_reads SET state='reading',ticket=?,expires=? WHERE entry_id=?",
                  (ticket, time.time()+600, row['id']))
        job['ticket'] = ticket
        job['comments'] = [dict(r) for r in c.execute('''SELECT u.name AS author,c.body,c.id
            FROM comments c JOIN users u ON c.user_id=u.id WHERE c.entry_id=?
            ORDER BY c.created,c.id''', (row['id'],))]
        for comment in job['comments']:
            comment['stickers'] = [s[0] for s in c.execute('''SELECT e.name FROM comment_emojis ce
                JOIN emojis e ON e.id=ce.emoji_id WHERE ce.comment_id=? ORDER BY position''',
                (comment.pop('id'),))]
        job['images'] = [r[0] for r in c.execute(
            "SELECT id FROM media WHERE entry_id=? AND kind='image' ORDER BY rowid", (row['id'],))]
        return {'job': job}


def active(c, ticket):
    row = c.execute("""SELECT w.entry_id FROM whale_reads w JOIN entries e ON e.id=w.entry_id
        AND e.day=w.day WHERE w.ticket=? AND w.state='reading' AND w.expires>=?""",
        (ticket, time.time())).fetchone()
    if not row:
        raise HTTPException(409, '这次读取已结束或帖子日期已变更')
    return row[0]


@router.get('/api/whale/agent/reads/{ticket}/images/{mid}')
def photo(ticket: str, mid: str, request: Request):
    agent(request)
    with db() as c:
        eid = active(c, ticket)
        row = c.execute("SELECT thumb FROM media WHERE id=? AND entry_id=? AND kind='image'",
                        (mid, eid)).fetchone()
    if not row or not row[0] or not (MEDIA / row[0]).is_file():
        raise HTTPException(404, '照片预览不可用')
    return {'jpeg': base64.b64encode((MEDIA / row[0]).read_bytes()).decode('ascii')}


@router.post('/api/whale/agent/reads/{ticket}/reply')
async def finish(ticket: str, request: Request):
    agent(request)
    _, body = await payload(request)
    if len(body) > 1000:
        raise HTTPException(400, '留言最多 1000 字')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute("SELECT state FROM whale_reads WHERE ticket=?", (ticket,)).fetchone()
        if old and old[0] == 'done':
            return {'ok': True}
        eid = active(c, ticket)
        c.execute("""UPDATE whale_reads SET state='done',reply=?,replied_at=?,expires=NULL
            WHERE entry_id=?""", (body, time.time(), eid))
    return {'ok': True}


@router.post('/api/whale/agent/reads/{ticket}/fail')
def fail(ticket: str, request: Request):
    agent(request)
    with db() as c:
        c.execute("UPDATE whale_reads SET state='failed',expires=NULL WHERE ticket=? AND state='reading'",
                  (ticket,))
    return {'ok': True}
