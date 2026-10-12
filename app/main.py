import asyncio, hashlib, hmac, json, os, secrets, sqlite3, subprocess, time, warnings
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

ROOT = Path(__file__).parent
DATA = Path(os.getenv('DATA_DIR', str(ROOT.parent / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
MEDIA = DATA / 'media'
MEDIA.mkdir(exist_ok=True)
PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://localhost:8000').rstrip('/')
MAX_FILE = 100 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)

@contextmanager
def db():
    c = sqlite3.connect(DATA / 'blue.db', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

with db() as c:
    c.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL);
    CREATE TABLE IF NOT EXISTS attempts(ip TEXT,t REAL);
    CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),day TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,entry_id TEXT REFERENCES entries(id) ON DELETE CASCADE,kind TEXT,mime TEXT,path TEXT,thumb TEXT);
    CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS comments_entry_created ON comments(entry_id,created);
    ''')

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

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

@app.middleware('http')
async def security(request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('x-blue-request') != '1':
            return JSONResponse({'detail':'请求校验失败'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != PUBLIC_URL:
            return JSONResponse({'detail':'来源不匹配，请检查 PUBLIC_URL'}, status_code=403)
        try:
            if int(request.headers.get('content-length', '0')) > MAX_TOTAL + 1024 * 1024:
                return JSONResponse({'detail':'一次上传不能超过 200 MB'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail':'无效请求'}, status_code=400)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith(('/api/', '/media/')):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.post('/api/login')
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

@app.get('/api/me')
def me(request: Request):
    return user(request)

@app.post('/api/logout')
def logout(request: Request):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE token=?', (token_hash(request.cookies.get('blue_session','')),))
    r = JSONResponse({'ok':True})
    r.delete_cookie('blue_session')
    return r

def records():
    with db() as c:
        entries = [dict(x) for x in c.execute('SELECT entries.*,users.name AS author FROM entries JOIN users ON users.id=entries.user_id ORDER BY day DESC,created DESC')]
        media = [dict(x) for x in c.execute('SELECT id,entry_id,kind,thumb FROM media')]
        comments = [dict(x) for x in c.execute('SELECT comments.*,users.name AS author FROM comments JOIN users ON users.id=comments.user_id ORDER BY comments.created,comments.id')]
    by_comment_entry = {}
    for comment in comments:
        by_comment_entry.setdefault(comment['entry_id'], []).append(comment)
    by_entry = {}
    for m in media:
        m['url'] = '/media/' + m['id']
        m['thumb'] = '/media/' + m['id'] + '/thumb' if m['thumb'] else None
        by_entry.setdefault(m.pop('entry_id'), []).append(m)
    for e in entries:
        e['media'] = by_entry.get(e['id'], [])
        e['comments'] = by_comment_entry.get(e['id'], [])
    return entries

@app.get('/api/entries')
def entries(request: Request):
    user(request)
    return records()

@app.get('/api/export')
def export(request: Request):
    user(request)
    return JSONResponse({'version':1,'entries':records()}, headers={'Content-Disposition':'attachment; filename="blue-days-records.json"'})

def make_image(source, dest):
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((640,640))
        im.convert('RGB').save(dest, 'JPEG', quality=82)

def validate_video(source):
    try:
        result = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name','-of','json',str(source)], check=True, capture_output=True, timeout=15)
        streams = json.loads(result.stdout).get('streams', [])
        return bool(streams and streams[0].get('codec_name') in ('h264', 'hevc', 'mpeg4', 'av1', 'vp9'))
    except (OSError, subprocess.SubprocessError, ValueError):
        return False

def video_thumb(source, dest):
    try:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),'-frames:v','1','-vf','scale=640:-2','-y',str(dest)], check=True, capture_output=True, timeout=25)
        return True
    except (OSError, subprocess.SubprocessError):
        dest.unlink(missing_ok=True)
        return False

@app.post('/api/entries')
async def create(request: Request):
    u = user(request)  # Authenticate before parsing large multipart bodies.
    paths = []
    try:
        async with request.form(max_files=12, max_fields=3, max_part_size=64*1024) as form:
            day = form.get('day','')
            body = form.get('body','')
            try:
                if date.fromisoformat(day).isoformat()!=day or len(body)>5000:
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400,'日期无效，或文字超过 5000 字')
            files = form.getlist('files')
            if not body.strip() and not files:
                raise HTTPException(400, '请写点文字或添加照片／视频')
            eid = secrets.token_hex(16)
            rows, total = [], 0
            for f in files:
                if not hasattr(f, 'read'):
                    raise HTTPException(400,'附件无效')
                mid = secrets.token_hex(16)
                path = MEDIA / mid
                paths.append(path)
                size = 0
                with path.open('wb') as out:
                    while chunk := await f.read(1024*1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size>MAX_FILE or total>MAX_TOTAL:
                            raise HTTPException(413, '单文件上限 100 MB，每次合计 200 MB')
                        out.write(chunk)
                thumb = MEDIA / (mid+'.jpg')
                paths.append(thumb)
                try:
                    await asyncio.to_thread(make_image,path,thumb)
                    with Image.open(path) as original:
                        kind, mime = 'image', Image.MIME.get(original.format, 'image/jpeg')
                except Exception:
                    with path.open('rb') as stream:
                        head = stream.read(32)
                    if head[4:8] != b'ftyp' or head[8:12] in (b'heic',b'heix',b'mif1',b'avif') or not await asyncio.to_thread(validate_video,path):
                        raise HTTPException(400,'支持 JPG、PNG、WebP 图片和 MP4／MOV 视频；HEIC 请先转为 JPG')
                    kind, mime = 'video', 'video/mp4'
                    await asyncio.to_thread(video_thumb,path,thumb)
                rows.append((mid,eid,kind,mime,mid,thumb.name if thumb.exists() else None))
            with db() as c:
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(eid,u['id'],day,body.strip(),time.time()))
                c.executemany('INSERT INTO media VALUES(?,?,?,?,?,?)',rows)
        return {'id':eid}
    except BaseException:
        for p in paths:
            p.unlink(missing_ok=True)
        raise

@app.delete('/api/entries/{eid}')
def delete(eid: str, request: Request):
    u = user(request)
    with db() as c:
        e = c.execute('SELECT user_id FROM entries WHERE id=?',(eid,)).fetchone()
        if not e:
            raise HTTPException(404,'记录不存在')
        if e['user_id']!=u['id']:
            raise HTTPException(403,'只能删除自己发布的记录')
        rows = c.execute('SELECT path,thumb FROM media WHERE entry_id=?',(eid,)).fetchall()
        c.execute('DELETE FROM entries WHERE id=?',(eid,))
    for row in rows:
        for name in row:
            if name:
                (MEDIA / name).unlink(missing_ok=True)
    return {'ok':True}

@app.post('/api/entries/{eid}/comments', status_code=201)
async def add_comment(eid: str, request: Request):
    u = user(request)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '评论格式无效')
    body = payload.get('body') if isinstance(payload, dict) else None
    if not isinstance(body, str) or not body.strip() or len(body) > 1000:
        raise HTTPException(400, '评论需填写 1–1000 字')
    comment = {'id': secrets.token_hex(16), 'entry_id': eid, 'user_id': u['id'],
               'author': u['name'], 'body': body.strip(), 'created': time.time()}
    with db() as c:
        # Lock before checking the parent so deletion cannot race the insert.
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM entries WHERE id=?', (eid,)).fetchone():
            raise HTTPException(404, '帖子已删除或不存在')
        c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',
                  (comment['id'], eid, u['id'], comment['body'], comment['created']))
    return comment

@app.delete('/api/comments/{cid}')
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

@app.get('/media/{mid}')
@app.get('/media/{mid}/thumb')
def media(mid: str, request: Request):
    user(request)
    with db() as c:
        m = c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
    if not m:
        raise HTTPException(404)
    is_thumb = request.url.path.endswith('/thumb')
    name = m['thumb'] if is_thumb else m['path']
    if not name or not (MEDIA/name).is_file():
        raise HTTPException(404)
    return FileResponse(MEDIA/name, media_type='image/jpeg' if is_thumb else m['mime'])

app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

@app.get('/')
def home():
    return FileResponse(ROOT/'static'/'index.html')

