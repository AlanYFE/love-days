"""Shared paths, resource limits and SQLite initialization."""
import asyncio
import os
import sqlite3
import warnings
from contextlib import contextmanager
from pathlib import Path
from PIL import Image

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
    CREATE TABLE IF NOT EXISTS monthly_memories(
        id TEXT PRIMARY KEY, month TEXT NOT NULL, payload TEXT NOT NULL,
        source_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL REFERENCES users(id), created REAL NOT NULL, updated REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS monthly_memories_month ON monthly_memories(month,updated);

    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL);
    CREATE TABLE IF NOT EXISTS attempts(ip TEXT,t REAL);
    CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),day TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,entry_id TEXT REFERENCES entries(id) ON DELETE CASCADE,kind TEXT,mime TEXT,path TEXT,thumb TEXT);
    CREATE TABLE IF NOT EXISTS tags(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE,user_id TEXT NOT NULL REFERENCES users(id),created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS entry_tags(entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,tag_id TEXT NOT NULL REFERENCES tags(id),PRIMARY KEY(entry_id,tag_id));
    CREATE INDEX IF NOT EXISTS entry_tags_tag ON entry_tags(tag_id,entry_id);
    CREATE TABLE IF NOT EXISTS activities(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('post','comment')),
        entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
        comment_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
        preview TEXT NOT NULL,created REAL NOT NULL,read_at REAL
    );
    CREATE INDEX IF NOT EXISTS activities_recipient_id ON activities(recipient_id,id);
    CREATE INDEX IF NOT EXISTS activities_unread ON activities(recipient_id,read_at);
    CREATE TABLE IF NOT EXISTS entry_locations(entry_id TEXT PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS media_extras(media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,display TEXT,motion TEXT,companion TEXT);
    CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS comment_media(id TEXT PRIMARY KEY,comment_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,position INTEGER NOT NULL,mime TEXT NOT NULL,path TEXT NOT NULL,thumb TEXT NOT NULL,display TEXT);
    CREATE INDEX IF NOT EXISTS comment_media_comment ON comment_media(comment_id,position);
    CREATE INDEX IF NOT EXISTS entries_day_created ON entries(day,created);
    CREATE INDEX IF NOT EXISTS media_entry ON media(entry_id);
    CREATE INDEX IF NOT EXISTS comments_entry_created ON comments(entry_id,created);
    CREATE TABLE IF NOT EXISTS emojis(id TEXT PRIMARY KEY,name TEXT NOT NULL,user_id TEXT NOT NULL REFERENCES users(id),mime TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS comment_emojis(comment_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,position INTEGER NOT NULL,emoji_id TEXT NOT NULL REFERENCES emojis(id),PRIMARY KEY(comment_id,position));
    CREATE TABLE IF NOT EXISTS entry_reactions(target_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,emoji_id TEXT NOT NULL REFERENCES emojis(id),user_id TEXT NOT NULL REFERENCES users(id),PRIMARY KEY(target_id,emoji_id,user_id));
    CREATE TABLE IF NOT EXISTS comment_reactions(target_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,emoji_id TEXT NOT NULL REFERENCES emojis(id),user_id TEXT NOT NULL REFERENCES users(id),PRIMARY KEY(target_id,emoji_id,user_id));
    ''')

