"""Application composition: middleware, feature routers and static files."""
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import auth, activities, comments, emojis, entries, locations, media, records, tags, monthly
from .core import ROOT, PUBLIC_URL, MAX_TOTAL
# Preserve earlier imports used by tests and maintenance commands.
from .core import db, MEDIA, EMOJI_DIR, MAX_EMOJI_BYTES
from .auth import password_hash
from .activities import add_activity

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
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src https://apis.map.qq.com https://mapapi.qq.com; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith(('/api/', '/media/')):
        response.headers['Cache-Control'] = 'no-store'
    return response


for feature in (auth, locations, activities, tags, records, entries, comments, emojis, media, monthly):
    app.include_router(feature.router)

app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

@app.get('/')
def home():
    return FileResponse(ROOT/'static'/'index.html')

