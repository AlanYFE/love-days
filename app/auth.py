"""Auth feature: routes and supporting logic."""
import asyncio
import hashlib
import hmac
import secrets
import time
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from .core import PUBLIC_URL, db

router = APIRouter()

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def user(request):
    token = request.cookies.get('blue_session', '')
    with db() as c:
        u = c.execute('SELECT users.id,users.name FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?', (token_hash(token), time.time())).fetchone()
    if not u:
        raise HTTPException(401, '请先登录')
    return dict(u)


@router.post('/api/login')
async def login(request: Request):
    ip = request.client.host if request.client else 'unknown'
    now = time.time()
    with db() as c:
        c.execute('DELETE FROM attempts WHERE t<?', (now-900,))
        if c.execute('SELECT count(*) FROM attempts WHERE ip=?', (ip,)).fetchone()[0] >= 12:
            raise HTTPException(429, '尝试次数过多，请 15 分钟后重试')
        c.execute('INSERT INTO attempts VALUES(?,?)', (ip, now))
    try:
        payload = await request.json()
        uid, password = payload.get('username', ''), payload.get('password', '')
        if not isinstance(uid, str) or not isinstance(password, str) or len(password)>256:
            raise ValueError()
    except Exception:
        raise HTTPException(400, '登录信息无效')
    with db() as c:
        account = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    salt = account['salt'] if account else '00' * 16
    actual = await asyncio.to_thread(password_hash, password, salt)
    if not account or not hmac.compare_digest(actual, account['password']):
        raise HTTPException(401, '账号或密码不正确')
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?', (now,))
        c.execute('INSERT INTO sessions VALUES(?,?,?)', (token_hash(token), uid, now+30*86400))
    r = JSONResponse({'id':uid,'name':account['name']})
    r.set_cookie('blue_session', token, max_age=30*86400, httponly=True, secure=PUBLIC_URL.startswith('https://'), samesite='strict')
    return r


@router.get('/api/me')
def me(request: Request):
    return user(request)


@router.post('/api/logout')
def logout(request: Request):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE token=?', (token_hash(request.cookies.get('blue_session','')),))
    r = JSONResponse({'ok':True})
    r.delete_cookie('blue_session')
    return r

