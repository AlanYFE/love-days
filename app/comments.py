"""Comments feature: routes and supporting logic."""
import secrets
import time
from fastapi import APIRouter, HTTPException, Request
from .activities import add_activity
from .auth import user
from .core import db

router = APIRouter()

@router.post('/api/entries/{eid}/comments', status_code=201)
async def add_comment(eid: str, request: Request):
    u = user(request)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '评论格式无效')
    body = payload.get('body') if isinstance(payload, dict) else None
    emoji_ids = payload.get('emoji_ids', []) if isinstance(payload, dict) else []
    if (not isinstance(body, str) or len(body) > 1000 or not isinstance(emoji_ids, list)
            or len(emoji_ids) > 8 or any(not isinstance(e, str) or len(e) != 32 for e in emoji_ids)
            or (not body.strip() and not emoji_ids)):
        raise HTTPException(400, '请输入评论或选择表情；最多 1000 字和 8 个表情')
    comment = {'id': secrets.token_hex(16), 'entry_id': eid, 'user_id': u['id'],
               'author': u['name'], 'body': body.strip(), 'created': time.time()}
    with db() as c:
        # Lock before checking the parent so deletion cannot race the insert.
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM entries WHERE id=?', (eid,)).fetchone():
            raise HTTPException(404, '帖子已删除或不存在')
        for emoji_id in emoji_ids:
            if not c.execute('SELECT 1 FROM emojis WHERE id=?', (emoji_id,)).fetchone():
                raise HTTPException(400, '所选表情不存在，请刷新表情库')
        c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',
                  (comment['id'], eid, u['id'], comment['body'], comment['created']))
        c.executemany('INSERT INTO comment_emojis VALUES(?,?,?)', [(comment['id'], i, e) for i,e in enumerate(emoji_ids)])
        add_activity(c,u['id'],'comment',eid,comment['body'] or '发送了表情留言',comment['id'])
    return comment


@router.delete('/api/comments/{cid}')
def delete_comment(cid: str, request: Request):
    u = user(request)
    with db() as c:
        comment = c.execute('SELECT user_id FROM comments WHERE id=?', (cid,)).fetchone()
        if not comment:
            raise HTTPException(404, '评论已删除或不存在')
        if comment['user_id'] != u['id']:
            raise HTTPException(403, '只能删除自己的评论')
        c.execute('DELETE FROM comments WHERE id=? AND user_id=?', (cid, u['id']))
    return {'ok': True}

