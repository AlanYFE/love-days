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
EMOJI_DIR = DATA / 'emojis'
EMOJI_DIR.mkdir(exist_ok=True)
MAX_EMOJI_BYTES = 5 * 1024 * 1024
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
    CREATE TABLE IF NOT EXISTS emojis(id TEXT PRIMARY KEY,name TEXT NOT NULL,user_id TEXT NOT NULL REFERENCES users(id),mime TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS comment_emojis(comment_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,position INTEGER NOT NULL,emoji_id TEXT NOT NULL REFERENCES emojis(id),PRIMARY KEY(comment_id,position));
    CREATE TABLE IF NOT EXISTS entry_reactions(target_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,emoji_id TEXT NOT NULL REFERENCES emojis(id),user_id TEXT NOT NULL REFERENCES users(id),PRIMARY KEY(target_id,emoji_id,user_id));
    CREATE TABLE IF NOT EXISTS comment_reactions(target_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,emoji_id TEXT NOT NULL REFERENCES emojis(id),user_id TEXT NOT NULL REFERENCES users(id),PRIMARY KEY(target_id,emoji_id,user_id));
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

def emoji_data(row):
    result = dict(row)
    result['url'] = '/api/emojis/' + result['id'] + '/image'
    return result

def reaction_map(c, table):
    # table is an internal constant, never a user-supplied SQL identifier.
    groups = {}
    for row in c.execute(f'SELECT r.target_id,r.user_id,e.id,e.name FROM {table} r JOIN emojis e ON e.id=r.emoji_id ORDER BY e.created,e.id,r.user_id'):
        group = groups.setdefault(row['target_id'], {})
        reaction = group.setdefault(row['id'], {'emoji':emoji_data({'id':row['id'],'name':row['name']}),'user_ids':[],'count':0})
        reaction['user_ids'].append(row['user_id'])
        reaction['count'] += 1
    return {key:list(value.values()) for key,value in groups.items()}

def records():
    with db() as c:
        entries = [dict(x) for x in c.execute('SELECT entries.*,users.name AS author FROM entries JOIN users ON users.id=entries.user_id ORDER BY day DESC,created DESC')]
        media = [dict(x) for x in c.execute('SELECT id,entry_id,kind,thumb FROM media')]
        comments = [dict(x) for x in c.execute('SELECT comments.*,users.name AS author FROM comments JOIN users ON users.id=comments.user_id ORDER BY comments.created,comments.id')]
        entry_reactions = reaction_map(c, 'entry_reactions')
        comment_reactions = reaction_map(c, 'comment_reactions')
        attached = {}
        for row in c.execute('SELECT ce.comment_id,e.id,e.name FROM comment_emojis ce JOIN emojis e ON e.id=ce.emoji_id ORDER BY ce.comment_id,ce.position'):
            attached.setdefault(row['comment_id'], []).append(emoji_data({'id':row['id'],'name':row['name']}))
    by_comment_entry = {}
    for comment in comments:
        comment['emojis'] = attached.get(comment['id'], [])
        comment['reactions'] = comment_reactions.get(comment['id'], [])
        by_comment_entry.setdefault(comment['entry_id'], []).append(comment)
    by_entry = {}
    for m in media:
        m['url'] = '/media/' + m['id']
        m['thumb'] = '/media/' + m['id'] + '/thumb' if m['thumb'] else None
        by_entry.setdefault(m.pop('entry_id'), []).append(m)
    for e in entries:
        e['media'] = by_entry.get(e['id'], [])
        e['comments'] = by_comment_entry.get(e['id'], [])
        e['reactions'] = entry_reactions.get(e['id'], [])
    return entries

@app.get('/api/entries')
def entries(request: Request):
    user(request)
    return records()

@app.get('/api/export')
def export(request: Request):
    user(request)
    return JSONResponse({'version':1,'entries':records()}, headers={'Content-Disposition':'attachment; filename="love-days-records.json"'})

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

def validate_emoji(path):
    try:
        with Image.open(path) as im:
            if im.format not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
                raise ValueError('format')
            mime = Image.MIME[im.format]
            frames = getattr(im, 'n_frames', 1)
            if max(im.size) > 2048 or frames > 200 or im.width * im.height * frames > 80_000_000:
                raise ValueError('dimensions')
            for index in range(frames):
                im.seek(index)
                im.load()
            return mime
    except Exception:
        raise HTTPException(400, '请使用有效的 JPG、PNG、WebP 或 GIF；最长边 2048 像素，动画最多 200 帧，总像素不超过 8000 万')

@app.get('/api/emojis')
def list_emojis(request: Request):
    user(request)
    with db() as c:
        return [emoji_data(row) for row in c.execute('SELECT id,name,user_id,created FROM emojis ORDER BY created DESC,id')]

@app.post('/api/emojis', status_code=201)
async def upload_emoji(request: Request):
    u = user(request)
    path = None
    try:
        async with request.form(max_files=1, max_fields=1, max_part_size=4096) as form:
            file = form.get('file')
            name = form.get('name', '')
            if not hasattr(file, 'read') or not isinstance(name, str) or not 1 <= len(name.strip()) <= 24:
                raise HTTPException(400, '请选择图片，并填写 1–24 字的表情名称')
            eid = secrets.token_hex(16)
            path = EMOJI_DIR / eid
            size = 0
            with path.open('wb') as out:
                while chunk := await file.read(256 * 1024):
                    size += len(chunk)
                    if size > MAX_EMOJI_BYTES:
                        raise HTTPException(413, '表情图片不能超过 5 MB')
                    out.write(chunk)
            mime = await asyncio.to_thread(validate_emoji, path)
            created = time.time()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT count(*) FROM emojis').fetchone()[0] >= 100:
                    raise HTTPException(400, '共享表情库最多保存 100 个表情')
                c.execute('INSERT INTO emojis VALUES(?,?,?,?,?)', (eid,name.strip(),u['id'],mime,created))
        return emoji_data({'id':eid,'name':name.strip(),'user_id':u['id'],'created':created})
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        raise

@app.get('/api/emojis/{eid}/image')
def emoji_image(eid: str, request: Request):
    user(request)
    with db() as c:
        row = c.execute('SELECT id,mime FROM emojis WHERE id=?', (eid,)).fetchone()
    if not row or not (EMOJI_DIR / row['id']).is_file():
        raise HTTPException(404, '表情不存在')
    return FileResponse(EMOJI_DIR / row['id'], media_type=row['mime'])

@app.put('/api/{kind}/{target_id}/reactions/{emoji_id}')
async def set_reaction(kind: str, target_id: str, emoji_id: str, request: Request):
    u = user(request)
    tables = {'entries':('entries','entry_reactions'), 'comments':('comments','comment_reactions')}
    if kind not in tables:
        raise HTTPException(404)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '回应格式无效')
    if not isinstance(payload, dict) or type(payload.get('active')) is not bool:
        raise HTTPException(400, '请指定是否选中表情')
    parent, table = tables[kind]
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute(f'SELECT 1 FROM {parent} WHERE id=?', (target_id,)).fetchone():
            raise HTTPException(404, '帖子或评论已删除')
        if not c.execute('SELECT 1 FROM emojis WHERE id=?', (emoji_id,)).fetchone():
            raise HTTPException(404, '表情不存在')
        if payload['active']:
            c.execute(f'INSERT OR IGNORE INTO {table} VALUES(?,?,?)', (target_id,emoji_id,u['id']))
        else:
            c.execute(f'DELETE FROM {table} WHERE target_id=? AND emoji_id=? AND user_id=?', (target_id,emoji_id,u['id']))
    return {'ok':True}

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

