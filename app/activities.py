"""Activities feature: routes and supporting logic."""
import time
from fastapi import APIRouter, HTTPException, Request
from .auth import user
from .core import db

router = APIRouter()

def add_activity(c, actor_id, kind, eid, preview, comment_id=None):
    # Run in the same transaction as publication, so failures create no ghost alerts.
    created=time.time()
    for row in c.execute('SELECT id FROM users WHERE id<>?',(actor_id,)).fetchall():
        c.execute('INSERT INTO activities(recipient_id,actor_id,kind,entry_id,comment_id,preview,created) VALUES(?,?,?,?,?,?,?)',
                  (row['id'],actor_id,kind,eid,comment_id,preview[:160],created))


@router.get('/api/activities')
def activities(request: Request, before: int = 0):
    u=user(request)
    if before<0 or before>9223372036854775807:
        raise HTTPException(400,'分页参数无效')
    with db() as c:
        c.execute('BEGIN')
        summary=c.execute('SELECT COALESCE(MAX(id),0) AS latest_id,COUNT(CASE WHEN read_at IS NULL THEN 1 END) AS unread FROM activities WHERE recipient_id=?',(u['id'],)).fetchone()
        rows=c.execute("""SELECT a.*,u.name AS actor,e.day FROM activities a
            JOIN users u ON u.id=a.actor_id JOIN entries e ON e.id=a.entry_id
            WHERE a.recipient_id=? AND (?=0 OR a.id<?) ORDER BY a.id DESC LIMIT 51""",(u['id'],before,before)).fetchall()
        items=[{k:r[k] for k in ('id','kind','entry_id','comment_id','preview','created','read_at','actor','day')} for r in rows[:50]]
    return {'items':items,'unread':summary['unread'],'latest_id':summary['latest_id'],
            'next_before':items[-1]['id'] if len(rows)>50 else None}


@router.post('/api/activities/read')
async def read_activities(request: Request):
    u=user(request)
    try:
        payload=await request.json()
        if not isinstance(payload,dict) or set(payload) not in ({'id'},{'through'}):
            raise ValueError()
        key=next(iter(payload));value=payload[key]
        if type(value) is not int or not 0<=value<=9223372036854775807:
            raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(400,'已读参数无效')
    with db() as c:
        if key=='id':
            if not c.execute('SELECT 1 FROM activities WHERE id=? AND recipient_id=?',(value,u['id'])).fetchone():
                raise HTTPException(404,'动态不存在')
            c.execute('UPDATE activities SET read_at=? WHERE id=? AND recipient_id=? AND read_at IS NULL',(time.time(),value,u['id']))
        else:
            c.execute('UPDATE activities SET read_at=? WHERE recipient_id=? AND id<=? AND read_at IS NULL',(time.time(),u['id'],value))
    return {'ok':True}

