"""Records feature: routes and supporting logic."""
import json
from datetime import date
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from .auth import user
from .core import db
from .emojis import emoji_data, reaction_map

router = APIRouter()

def records(day=None, month=None):
    with db() as c:
        c.execute('BEGIN')
        c.execute('CREATE TEMP TABLE record_scope(id TEXT PRIMARY KEY)')
        if month is not None:
            c.execute('INSERT INTO record_scope SELECT id FROM entries WHERE day>=? AND day<=?', (month+'-01', month+'-31'))
        elif day is None:
            c.execute('INSERT INTO record_scope SELECT id FROM entries')
        else:
            c.execute('INSERT INTO record_scope SELECT id FROM entries WHERE day=?', (day,))
        entries = [dict(x) for x in c.execute('SELECT entries.*,users.name AS author FROM entries JOIN users ON users.id=entries.user_id WHERE entries.id IN (SELECT id FROM record_scope) ORDER BY day DESC,created DESC,id DESC')]
        media = [dict(x) for x in c.execute('SELECT id,entry_id,kind,thumb FROM media WHERE entry_id IN (SELECT id FROM record_scope) ORDER BY rowid')]
        extras = {r['media_id']:dict(r) for r in c.execute('SELECT * FROM media_extras WHERE media_id IN (SELECT id FROM media WHERE entry_id IN (SELECT id FROM record_scope))')}
        comments = [dict(x) for x in c.execute('SELECT comments.*,users.name AS author FROM comments JOIN users ON users.id=comments.user_id WHERE comments.entry_id IN (SELECT id FROM record_scope) ORDER BY comments.created,comments.id')]
        entry_reactions = reaction_map(c, 'entry_reactions', 'SELECT id FROM record_scope')
        comment_reactions = reaction_map(c, 'comment_reactions', 'SELECT id FROM comments WHERE entry_id IN (SELECT id FROM record_scope)')
        locations = {r['entry_id']:json.loads(r['payload']) for r in c.execute('SELECT * FROM entry_locations WHERE entry_id IN (SELECT id FROM record_scope)')}
        tagged = {}
        for row in c.execute('SELECT et.entry_id,t.id,t.name FROM entry_tags et JOIN tags t ON t.id=et.tag_id WHERE et.entry_id IN (SELECT id FROM record_scope) ORDER BY t.created,t.id'):
            tagged.setdefault(row['entry_id'], []).append({'id':row['id'],'name':row['name']})
        attached = {}
        for row in c.execute('SELECT ce.comment_id,e.id,e.name FROM comment_emojis ce JOIN emojis e ON e.id=ce.emoji_id WHERE ce.comment_id IN (SELECT id FROM comments WHERE entry_id IN (SELECT id FROM record_scope)) ORDER BY ce.comment_id,ce.position'):
            attached.setdefault(row['comment_id'], []).append(emoji_data({'id':row['id'],'name':row['name']}))
    by_comment_entry = {}
    for comment in comments:
        comment['emojis'] = attached.get(comment['id'], [])
        comment['reactions'] = comment_reactions.get(comment['id'], [])
        by_comment_entry.setdefault(comment['entry_id'], []).append(comment)
    by_entry = {}
    for m in media:
        extra = extras.get(m['id'], {})
        m['live'] = bool(extra.get('motion'))
        m['motion_url'] = '/media/' + m['id'] + '/motion' if m['live'] else None
        m['original_url'] = '/media/' + m['id'] + '/original' if extra else None
        m['url'] = '/media/' + m['id']
        m['thumb'] = '/media/' + m['id'] + '/thumb' if m['thumb'] else None
        by_entry.setdefault(m.pop('entry_id'), []).append(m)
    for e in entries:
        e['location'] = locations.get(e['id'])
        e['tags'] = tagged.get(e['id'], [])
        e['media'] = by_entry.get(e['id'], [])
        e['comments'] = by_comment_entry.get(e['id'], [])
        e['reactions'] = entry_reactions.get(e['id'], [])
    return entries


@router.get('/api/entries')
def entries(request: Request, day: str | None = None):
    user(request)
    if day is not None:
        try:
            parsed = date.fromisoformat(day)
            if parsed.isoformat() != day or not 1900 <= parsed.year <= 2200:
                raise ValueError()
        except ValueError:
            raise HTTPException(400, '日期格式不正确')
    return records(day)


@router.get('/api/calendar')
def calendar_summary(request: Request):
    user(request)
    with db() as c:
        c.execute('BEGIN')
        days = [dict(r) for r in c.execute("""
            WITH summary AS (SELECT day, COUNT(*) AS count,
              (SELECT substr(e.body,1,120) FROM entries e WHERE e.day=entries.day
               ORDER BY e.created DESC,e.id DESC LIMIT 1) AS excerpt,
              (SELECT m.id FROM entries e JOIN media m ON m.entry_id=e.id
               WHERE e.day=entries.day AND m.thumb IS NOT NULL AND m.thumb!=''
               ORDER BY e.created DESC,e.id DESC,m.rowid LIMIT 1) AS cover_id
            FROM entries GROUP BY day)
            SELECT summary.*, media.kind AS cover_kind FROM summary
            LEFT JOIN media ON media.id=summary.cover_id ORDER BY summary.day
        """)]
        media_count = c.execute('SELECT COUNT(*) FROM media').fetchone()[0]
    for d in days:
        mid, kind = d.pop('cover_id'), d.pop('cover_kind')
        d['cover'] = {'thumb':f'/media/{mid}/thumb', 'kind':kind} if mid else None
    return {'days':days, 'stats':{'days':len(days), 'entries':sum(d['count'] for d in days), 'media':media_count}}


@router.get('/api/entries/{eid}')
def entry_location(request: Request, eid: str):
    user(request)
    with db() as c:
        row = c.execute('SELECT id,day FROM entries WHERE id=?', (eid,)).fetchone()
    if not row:
        raise HTTPException(404, '这条帖子已删除')
    return dict(row)


@router.get('/api/export')
def export(request: Request):
    user(request)
    return JSONResponse({'version':1,'entries':records()}, headers={'Content-Disposition':'attachment; filename="love-days-records.json"'})


@router.get('/api/anniversaries')
def anniversaries(request: Request):
    user(request)
    return {'together':'2026-03-21','birthdays':[
        {'name':'飞飞','day':'2000-09-22'},
        {'name':'巧巧','day':'2000-08-25'},
    ]}

