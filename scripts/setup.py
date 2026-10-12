"""Run interactively on the server; passwords are never printed or saved in plaintext."""
import getpass, os, secrets, sqlite3, hashlib
from pathlib import Path
folder=Path(os.getenv('DATA_DIR','data'))
folder.mkdir(parents=True,exist_ok=True)
con=sqlite3.connect(folder/'blue.db')
con.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL)')
if con.execute('SELECT count(*) FROM users').fetchone()[0]: raise SystemExit('已有账号；初始化已停止，避免额外创建用户。')
for i in (1,2):
    uid=input(f'第 {i} 位登录账号（英文字母/数字）: ').strip()
    if not uid.isascii() or not uid.isalnum(): raise SystemExit('账号请使用英文字母和数字')
    if con.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise SystemExit('该账号已存在；不覆盖已有用户')
    name=input('显示昵称: ').strip()[:30] or uid
    pwd=getpass.getpass('密码（至少 6 位）: ')
    if len(pwd)<6 or len(pwd)>256 or pwd!=getpass.getpass('再次输入密码: '): raise SystemExit('密码长度不合适或两次不一致')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',pwd.encode(),bytes.fromhex(salt),600000).hex()
    con.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,name,salt,digest))
con.commit()
con.close()
print('两个账号已创建；登录后自动进入同一个空间。')
