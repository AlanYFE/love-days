"""Private monthly memory drafts. No external AI calls until a provider is chosen."""
import hashlib
import json
import re
import secrets
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Request
from .auth import user
from .core import db
from .records import records

router = APIRouter()


def valid_month(value):
    if not isinstance(value, str) or not re.fullmatch(r'(19\d{2}|20\d{2}|21\d{2}|2200)-(0[1-9]|1[0-2])', value):
        raise HTTPException(400, '请选择有效的年份和月份')
    return value


def digest(entries):
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def statistics(entries):
    tags = Counter(t['name'] for e in entries for t in e['tags'])
    return dict(days=len({e['day'] for e in entries}), posts=len(entries),
                photos=sum(m['kind']=='image' for e in entries for m in e['media']),
                videos=sum(m['kind']=='video' for e in entries for m in e['media']),
                comments=sum(len(e['comments']) for e in entries),
                tags=[{'name':k,'count':v} for k,v in tags.most_common(10)])


def pack(row, entries=None):
    result = dict(row)
    result['payload'] = json.loads(result['payload'])
    if entries is not None:
        ids = set(result['payload']['entry_ids'])
        result['source_changed'] = digest([e for e in entries if e['id'] in ids]) != result['source_hash']
        result['new_records'] = sum(e['id'] not in ids for e in entries)
    return result


async def body(request):
    try:
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise HTTPException(400, '回忆内容格式无效')


def ids(value, available, limit=None):
    if (not isinstance(value, list) or any(not isinstance(x,str) for x in value)
            or len(set(value)) != len(value) or (limit is not None and len(value)>limit)
            or not set(value).issubset(available)):
        raise HTTPException(400, '选择的记录或照片无效，请刷新后重试')
    return value


@router.get('/api/monthly/{month}')
def overview(month: str, request: Request):
    user(request); valid_month(month)
    entries = records(month=month)
    with db() as c:
        memories = [pack(r, entries) for r in c.execute('SELECT * FROM monthly_memories WHERE month=? ORDER BY updated DESC,id', (month,))]
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    return {'month':month,'as_of':today,'entries':entries,'stats':statistics(entries),
            'memories':memories,'ai_available':False}


@router.post('/api/monthly/{month}', status_code=201)
async def create(month: str, request: Request):
    u = user(request); valid_month(month)
    value = await body(request)
    entries = records(month=month)
    selected = ids(value.get('entry_ids'), {e['id'] for e in entries})
    if not selected:
        raise HTTPException(400, '请至少选择一条记录')
    entries = [e for e in entries if e['id'] in selected]
    photo_ids = [m['id'] for e in entries for m in e['media'] if m['kind']=='image']
    payload = {'title':month.replace('-', ' 年 ')+' 月 · 我们的回忆','body':'',
               'entry_ids':selected,'highlights':[e['id'] for e in entries[:6]],
               'cover_id':photo_ids[0] if photo_ids else None,
               'notes':{},'status':'draft','stats':statistics(entries),'origin':'manual',
               'as_of':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()}
    now = time.time(); mid = secrets.token_hex(16)
    with db() as c:
        c.execute('INSERT INTO monthly_memories VALUES(?,?,?,?,?,?,?,?)',
                  (mid,month,json.dumps(payload,ensure_ascii=False),digest(entries),1,u['id'],now,now))
        row = c.execute('SELECT * FROM monthly_memories WHERE id=?',(mid,)).fetchone()
    return pack(row, entries)


@router.put('/api/monthly/{month}/{mid}')
async def update(month: str, mid: str, request: Request):
    u = user(request); valid_month(month)
    value = await body(request)
    if type(value.get('revision')) is not int:
        raise HTTPException(400,'缺少版本信息，请刷新后重试')
    for key, maximum in [('title',100),('body',8000),('note',500)]:
        if not isinstance(value.get(key),str) or len(value[key])>maximum:
            raise HTTPException(400, '标题、正文或留言超过长度限制')
    if not value['title'].strip() or value.get('status') not in ('draft','saved'):
        raise HTTPException(400,'请填写标题并选择保存状态')
    entries = records(month=month)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM monthly_memories WHERE id=? AND month=?',(mid,month)).fetchone()
        if not row:
            raise HTTPException(404,'这份回忆不存在')
        if row['revision'] != value['revision']:
            raise HTTPException(409,'对方刚刚修改了这份回忆。请先复制你的文字，再重新打开最新版本。')
        p = json.loads(row['payload'])
        selected = [e for e in entries if e['id'] in p['entry_ids']]
        # Existing references may have been deleted; allow removing them during editing.
        highlights = ids(value.get('highlights'), set(p['entry_ids']), 6)
        photos = {m['id'] for e in selected for m in e['media'] if m['kind']=='image'}
        cover = value.get('cover_id')
        if cover is not None and (not isinstance(cover,str) or cover not in photos):
            raise HTTPException(400,'封面照片已不存在，请重新选择封面或选择无封面')
        p.update(title=value['title'].strip(),body=value['body'],status=value['status'],
                 cover_id=cover,highlights=highlights)
        p['notes'][u['id']]={'name':u['name'],'text':value['note']}
        c.execute('UPDATE monthly_memories SET payload=?,revision=revision+1,updated=? WHERE id=?',
                  (json.dumps(p,ensure_ascii=False),time.time(),mid))
        result = c.execute('SELECT * FROM monthly_memories WHERE id=?',(mid,)).fetchone()
    return pack(result, entries)
