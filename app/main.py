import asyncio, hashlib, hmac, json, os, secrets, sqlite3, subprocess, time, warnings, unicodedata
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from .live import motion_range, extract_motion, still_jpeg, transcode_motion

ROOT = Path(__file__).parent
DATA = Path(os.getenv('DATA_DIR', str(ROOT.parent / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
MEDIA = DATA / 'media'
MEDIA.mkdir(exist_ok=True)
EMOJI_DIR = DATA / 'emojis'
EMOJI_DIR.mkdir(exist_ok=True)
MAX_EMOJI_BYTES = 5 * 1024 * 1024
PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://localhost:8000').rstrip('/')
LIVE_PROCESSING = asyncio.Semaphore(1)
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
    CREATE TABLE IF NOT EXISTS tags(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE,user_id TEXT NOT NULL REFERENCES users(id),created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS entry_tags(entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,tag_id TEXT NOT NULL REFERENCES tags(id),PRIMARY KEY(entry_id,tag_id));
    CREATE INDEX IF NOT EXISTS entry_tags_tag ON entry_tags(tag_id,entry_id);
    CREATE TABLE IF NOT EXISTS media_extras(media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,display TEXT,motion TEXT,companion TEXT);
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

@app.get('/api/anniversaries')
def anniversaries(request: Request):
    user(request)
    return {'together':'2026-03-21','birthdays':[
        {'name':'飞飞','day':'2000-09-22'},
        {'name':'巧巧','day':'2000-08-25'},
    ]}

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

MAX_TAGS = 200
MAX_ENTRY_TAGS = 8

def validate_tag_ids(value):
    if not isinstance(value, list) or len(value) > MAX_ENTRY_TAGS or any(not isinstance(t, str) or len(t) != 32 for t in value):
        raise HTTPException(400, '每条记录最多选择 8 个有效标签')
    return list(dict.fromkeys(value))

def check_tags(c, tag_ids):
    for tid in tag_ids:
        if not c.execute('SELECT 1 FROM tags WHERE id=?', (tid,)).fetchone():
            raise HTTPException(400, '所选标签不存在，请重新选择')

@app.get('/api/tags')
def list_tags(request: Request):
    user(request)
    with db() as c:
        return [dict(r) for r in c.execute('SELECT id,name FROM tags ORDER BY created,name_key')]

@app.post('/api/tags')
async def create_tag(request: Request):
    u = user(request)
    try:
        payload = await request.json()
        name = payload.get('name') if isinstance(payload, dict) else None
        if not isinstance(name, str) or len(name) > 200:
            raise ValueError()
        name = ' '.join(unicodedata.normalize('NFKC', name).split())
        if not 1 <= len(name) <= 24 or any(unicodedata.category(ch) == 'Cc' for ch in name):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, '标签名称请填写 1–24 个字')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute('SELECT id,name FROM tags WHERE name_key=?', (name.casefold(),)).fetchone()
        if existing:
            return JSONResponse(dict(existing), status_code=200)
        if c.execute('SELECT count(*) FROM tags').fetchone()[0] >= MAX_TAGS:
            raise HTTPException(400, '共享标签库最多保存 200 个标签，请选择已有标签')
        tag = {'id':secrets.token_hex(16), 'name':name}
        c.execute('INSERT INTO tags VALUES(?,?,?,?,?)', (tag['id'],name,name.casefold(),u['id'],time.time()))
    return JSONResponse(tag, status_code=201)

def records():
    with db() as c:
        entries = [dict(x) for x in c.execute('SELECT entries.*,users.name AS author FROM entries JOIN users ON users.id=entries.user_id ORDER BY day DESC,created DESC')]
        media = [dict(x) for x in c.execute('SELECT id,entry_id,kind,thumb FROM media')]
        extras = {r['media_id']:dict(r) for r in c.execute('SELECT * FROM media_extras')}
        comments = [dict(x) for x in c.execute('SELECT comments.*,users.name AS author FROM comments JOIN users ON users.id=comments.user_id ORDER BY comments.created,comments.id')]
        entry_reactions = reaction_map(c, 'entry_reactions')
        comment_reactions = reaction_map(c, 'comment_reactions')
        tagged = {}
        for row in c.execute('SELECT et.entry_id,t.id,t.name FROM entry_tags et JOIN tags t ON t.id=et.tag_id ORDER BY t.created,t.id'):
            tagged.setdefault(row['entry_id'], []).append({'id':row['id'],'name':row['name']})
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
        extra = extras.get(m['id'], {})
        m['live'] = bool(extra.get('motion'))
        m['motion_url'] = '/media/' + m['id'] + '/motion' if m['live'] else None
        m['original_url'] = '/media/' + m['id'] + '/original' if extra else None
        m['url'] = '/media/' + m['id']
        m['thumb'] = '/media/' + m['id'] + '/thumb' if m['thumb'] else None
        by_entry.setdefault(m.pop('entry_id'), []).append(m)
    for e in entries:
        e['tags'] = tagged.get(e['id'], [])
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
        async with request.form(max_files=24, max_fields=4, max_part_size=64*1024) as form:
            day = form.get('day','')
            body = form.get('body','')
            try:
                if date.fromisoformat(day).isoformat()!=day or len(body)>5000:
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400,'日期无效，或文字超过 5000 字')
            try:
                tag_ids = validate_tag_ids(json.loads(form.get('tag_ids', '[]')))
            except (ValueError, TypeError):
                raise HTTPException(400, '标签格式无效')
            with db() as c:
                check_tags(c, tag_ids)
            files = form.getlist('files')
            if len(files) > 12:
                raise HTTPException(400, '每条记录最多 12 个附件')
            try:
                options = json.loads(form.get('live_options', 'null'))
                if options is not None and (not isinstance(options, list) or len(options) != len(files) or any(not isinstance(o, dict) or type(o.get('enabled')) is not bool or type(o.get('paired')) is not bool for o in options)):
                    raise ValueError()
                for key,value in form.multi_items():
                    if hasattr(value, 'read') and key != 'files' and (options is None or key not in {f'live_{i}' for i,o in enumerate(options) if o['enabled'] and o['paired']}):
                        raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400, '实况选项无效，请重新选择附件')
            if not body.strip() and not files:
                raise HTTPException(400, '请写点文字或添加照片／视频')
            eid = secrets.token_hex(16)
            rows, extra_rows, total = [], [], 0
            for index, f in enumerate(files):
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
                display = motion = companion = None
                try:
                    await asyncio.to_thread(make_image,path,thumb)
                    with Image.open(path) as original:
                        kind, mime = 'image', Image.MIME.get(original.format, 'image/jpeg')
                        heif = original.format in ('HEIF', 'AVIF')
                except Exception:
                    with path.open('rb') as stream:
                        head = stream.read(32)
                    if head[4:8] != b'ftyp' or head[8:12] in (b'heic',b'heix',b'mif1',b'avif') or not await asyncio.to_thread(validate_video,path):
                        raise HTTPException(400,'图片或视频无法读取，请使用 JPG、PNG、WebP、HEIC 或 MP4／MOV')
                    kind, mime = 'video', 'video/mp4'
                    await asyncio.to_thread(video_thumb,path,thumb)
                choice = options[index] if options is not None else {'enabled':True,'paired':False}
                if kind == 'image':
                    try:
                        # A damaged live file can still be explicitly saved as a still.
                        span = await asyncio.to_thread(motion_range,path) if choice['enabled'] else None
                        if choice['paired'] and choice['enabled']:
                            fpair = form.get('live_'+str(index))
                            if not hasattr(fpair, 'read'):
                                raise ValueError('请补选实况对应的视频')
                            companion = MEDIA / (mid+'.source.mov')
                            paths.append(companion)
                            pair_size = 0
                            with companion.open('wb') as out:
                                while chunk := await fpair.read(1024*1024):
                                    pair_size += len(chunk)
                                    total += len(chunk)
                                    if pair_size > MAX_FILE or total > MAX_TOTAL:
                                        raise HTTPException(413, '配套视频计入上传限制：单个 100 MB，合计 200 MB')
                                    out.write(chunk)
                        elif span:
                            companion = MEDIA / (mid+'.source.mov')
                            paths.append(companion)
                            await asyncio.to_thread(extract_motion,path,companion,span)
                        elif options is not None and choice['enabled']:
                            raise ValueError('没有收到实况视频，请从文件中选择原图、补选配套视频，或取消保留实况')
                        if companion:
                            motion = MEDIA / (mid+'.live.mp4')
                            paths.append(motion)
                            async with LIVE_PROCESSING:
                                await asyncio.to_thread(transcode_motion,companion,motion)
                        if heif or motion:
                            display = MEDIA / (mid+'.display.jpg')
                            paths.append(display)
                            await asyncio.to_thread(still_jpeg,path,display)
                        elif not choice['enabled']:
                            # Strip embedded motion when the user chooses "still only".
                            with path.open('rb') as stream:
                                head = stream.read(1024*1024)
                            if b'MotionPhoto' in head or b'MicroVideo' in head:
                                display = MEDIA / (mid+'.display.jpg')
                                paths.append(display)
                                await asyncio.to_thread(still_jpeg,path,display)
                                display.replace(path)
                                display = None
                                mime = 'image/jpeg'
                    except ValueError as exc:
                        raise HTTPException(400, str(exc))
                    if display or motion or companion:
                        extra_rows.append((mid,display.name if display else None,motion.name if motion else None,companion.name if companion else None))
                elif options is not None and (choice['enabled'] or choice['paired']):
                    raise HTTPException(400, '实况选项只适用于照片')
                rows.append((mid,eid,kind,mime,mid,thumb.name if thumb.exists() else None))
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                check_tags(c, tag_ids)
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(eid,u['id'],day,body.strip(),time.time()))
                c.executemany('INSERT INTO media VALUES(?,?,?,?,?,?)',rows)
                c.executemany('INSERT INTO media_extras VALUES(?,?,?,?)',extra_rows)
                c.executemany('INSERT INTO entry_tags VALUES(?,?)', [(eid,tid) for tid in tag_ids])
        return {'id':eid}
    except BaseException:
        for p in paths:
            p.unlink(missing_ok=True)
        raise

@app.patch('/api/entries/{eid}')
async def edit_entry(eid: str, request: Request):
    u = user(request)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError()
        day, body = payload.get('day'), payload.get('body')
        if not isinstance(day, str) or not isinstance(body, str) or len(body) > 5000:
            raise ValueError()
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day or not 1900 <= parsed.year <= 2200:
            raise ValueError()
        original = payload.get('original')
        if not isinstance(original, dict) or not all(isinstance(original.get(k), str) for k in ('day', 'body')):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, '编辑内容无效：请检查日期和文字（最多 5000 字）')
    tag_ids = validate_tag_ids(payload['tag_ids']) if 'tag_ids' in payload else None
    original_tags = validate_tag_ids(original.get('tag_ids')) if tag_ids is not None else None
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        entry = c.execute('SELECT * FROM entries WHERE id=?', (eid,)).fetchone()
        if not entry:
            raise HTTPException(404, '帖子已删除或不存在')
        if entry['user_id'] != u['id']:
            raise HTTPException(403, '只能编辑自己发布的记录')
        if any(entry[k] != original[k] for k in ('day', 'body')):
            raise HTTPException(409, '这条记录已在其他页面修改，请保留草稿，关闭并刷新后重新编辑')
        if tag_ids is not None:
            current_tags = {r['tag_id'] for r in c.execute('SELECT tag_id FROM entry_tags WHERE entry_id=?', (eid,))}
            if current_tags != set(original_tags):
                raise HTTPException(409, '标签已在其他页面修改，请保留草稿，关闭并刷新后重新编辑')
            check_tags(c, tag_ids)
        if not body.strip() and not c.execute('SELECT 1 FROM media WHERE entry_id=?', (eid,)).fetchone():
            raise HTTPException(400, '没有附件的记录不能清空文字')
        c.execute('UPDATE entries SET day=?,body=? WHERE id=?', (day, body.strip(), eid))
        if tag_ids is not None:
            c.execute('DELETE FROM entry_tags WHERE entry_id=?', (eid,))
            c.executemany('INSERT INTO entry_tags VALUES(?,?)', [(eid,tid) for tid in tag_ids])
    return {'ok': True, 'id': eid, 'day': day}

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
        rows += c.execute('SELECT x.display,x.motion,x.companion FROM media_extras x JOIN media m ON m.id=x.media_id WHERE m.entry_id=?',(eid,)).fetchall()
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
@app.get('/media/{mid}/motion')
@app.get('/media/{mid}/original')
def media(mid: str, request: Request):
    user(request)
    with db() as c:
        m = c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
        extra = c.execute('SELECT * FROM media_extras WHERE media_id=?',(mid,)).fetchone()
    if not m:
        raise HTTPException(404)
    suffix = request.url.path.rsplit('/',1)[-1]
    name, mime = m['path'], m['mime']
    if suffix == 'thumb':
        name, mime = m['thumb'], 'image/jpeg'
    elif suffix == 'motion':
        name, mime = extra['motion'] if extra else None, 'video/mp4'
    elif suffix != 'original' and extra and extra['display']:
        name, mime = extra['display'], 'image/jpeg'
    if not name or not (MEDIA/name).is_file():
        raise HTTPException(404)
    return FileResponse(MEDIA/name, media_type=mime)

app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

@app.get('/')
def home():
    return FileResponse(ROOT/'static'/'index.html')
