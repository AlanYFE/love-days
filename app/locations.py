"""Locations feature: routes and supporting logic."""
import json
import math
import os
import unicodedata
from fastapi import APIRouter, HTTPException, Request
from .auth import user

router = APIRouter()

def validate_location(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HTTPException(400, '地点格式无效')
    result = {}
    for field, limit in (('name',120),('city',80),('address',300)):
        text = value.get(field, '')
        if not isinstance(text, str) or len(text)>limit or any(unicodedata.category(ch)=='Cc' for ch in text):
            raise HTTPException(400, '地点名称、城市或地址格式无效')
        result[field] = text.strip()
    if not result['name']:
        raise HTTPException(400, '请填写地点名称')
    lat, lng = value.get('lat'), value.get('lng')
    if lat is None and lng is None:
        result.update(lat=None,lng=None,source='manual',coordinate_system=None)
    elif (type(lat) in (int,float) and type(lng) in (int,float)
          and math.isfinite(lat) and math.isfinite(lng) and -90<=lat<=90 and -180<=lng<=180
          and value.get('coordinate_system')=='gcj02' and value.get('source')=='tencent'):
        result.update(lat=lat,lng=lng,source='tencent',coordinate_system='gcj02')
    else:
        raise HTTPException(400, '地点坐标无效，请重新选点')
    return result


def stored_location(c, eid):
    row=c.execute('SELECT payload FROM entry_locations WHERE entry_id=?',(eid,)).fetchone()
    return json.loads(row['payload']) if row else None


def save_location(c, eid, location):
    c.execute('DELETE FROM entry_locations WHERE entry_id=?',(eid,))
    if location is not None:
        c.execute('INSERT INTO entry_locations VALUES(?,?)',(eid,json.dumps(location,ensure_ascii=False)))


@router.get('/api/map-config')
def map_config(request: Request):
    user(request)
    return {'key':os.getenv('TENCENT_MAP_KEY','').strip(),'referer':'LoveDays'}

