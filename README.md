# 蓝色日记 · 快速试用版

两个人共同使用的私密照片日历。独立部署，不依赖 OpenAI 账号或海外前端 CDN。

## 已实现

- 手机适配的照片月历、全年蓝色热力图；一天一个格子。
- 热度按**发布记录数**计算：0、1、2–3、4–6、7+ 五档。照片封面下方的蓝色边条显示热度，避免蓝色蒙层盖住照片。
- 每条记录支持文字与多附件；支持补记旧日期。日期以用户选择的日期为准，不随服务器时区变化。
- 两个独立账号，共享全部记录；只允许删除自己发布的记录。
- JPG、PNG、WebP、GIF 图片与 MP4/MOV 视频；自动生成封面，原始图片保留。
- 登录后才能读取原图、视频与缩略图；密码使用 PBKDF2 哈希，登录限速、HttpOnly 会话 Cookie、请求来源校验。
- 上传进度、错误提示，每 30 秒刷新对方的新记录。
- 导出记录 JSON；服务器全量备份脚本。

这是已可运行的试用源码，**尚未部署到你的腾讯云账号**，没有公开网址。自动化接口测试与前端构建已完成；未做真实手机浏览器和中国大陆网络实测，Docker 部署流程未在本环境实机运行。

## 最快部署路线

### 1. 在腾讯云准备

1. 注册一个普通域名，按购买页面完成实名认证。域名购买后不需要转移给任何人。
2. 购买**轻量应用服务器 Lighthouse，中国香港地域**，选择 Ubuntu 24.04 LTS 系统镜像。试用建议 2 核 2 GB 起步、至少 40 GB 磁盘；最终以控制台可售套餐为准。暂时按月购买，先验证你们双方的网络。
3. 暂时不用购买数据库、COS、CDN、付费 SSL。试用版将照片、视频和 SQLite 存在服务器的 `data/` 目录。
4. 在服务器防火墙开放 TCP 80、443，SSH 22 尽量仅允许你自己的 IP。UDP 443 可选。**不开放 8000 和数据库端口。**
5. 在 DNS 解析添加 A 记录：主机记录 `love`，记录值为服务器公网 IPv4。
6. 最终地址形如 `https://love.你的域名.com`。如不配置 IPv6，请勿添加 AAAA 记录。

香港网站不走中国大陆服务器的网站接入备案流程，但跨境网络受运营商线路影响，不能保证每条国内网络都快。域名能注册不等于网络已经可访问；需部署后实际验证。

### 2. 上传和配置

通过腾讯云控制台 SSH 或自己电脑的 SSH 登录服务器。按 Docker 官方 Ubuntu 文档安装 Docker Engine 与 Compose 插件：
https://docs.docker.com/engine/install/ubuntu/

确认：

```bash
docker --version
docker compose version
```

把整个 `blue-days` 文件夹传到服务器，例如 `/opt/blue-days`。以下命令都在该目录中执行：

```bash
cd /opt/blue-days
cp .env.example .env
nano .env
```

将 `.env` 改为你的实际域名（不带 `https://` 和结尾斜杠）：

```dotenv
DOMAIN=love.your-domain.com
```

初始化两个账号。昵称与密码只在你自己的终端输入，不要发到聊天里：

```bash
docker compose build
docker compose run --rm app python scripts/setup.py
docker compose up -d
```

初始化脚本仅在没有任何账号时运行，防止意外添加第三人。第一次构建需要下载 Python 依赖、基础镜像和 ffmpeg。

Caddy 在域名解析正确、80/443 可访问时自动申请并续期 HTTPS 证书。等待启动后，在手机浏览器打开你的 HTTPS 地址，用刚才创建的账号登录。再给女朋友域名和她的账号。

**没有域名时**可以先在电脑上本地试运行；正式远程上传私密图片请等 HTTPS 配置好。这里只交付独立部署代码，不使用 OpenAI Sites 托管。

### 3. 上线检查

- 两台手机分别登录，A 上传照片与文字，B 在 30 秒内或刷新后能看到。
- 上传一段小 MP4，确认封面、播放、拖动进度正常。
- 退出登录后，直接访问原图地址应该提示未登录。
- HTTPS 无证书警告。
- 微信内打开和系统浏览器分别测试。微信可能对新域名提示风险，本站不能控制该提示；可先用系统浏览器访问。

### 4. 排查

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose logs --tail=100 caddy
```

- 网站打不开：检查 A 记录、公网 IP、80/443、防火墙和域名拼写。
- 登录提示“来源不匹配”：检查 `.env` 的 DOMAIN 与打开的域名完全一致；更改后执行 `docker compose up -d`。
- HTTPS 申请失败：检查 80 和 443 端口以及错误的 AAAA 记录；不要短时间反复重建证书存储卷。
- 视频上传慢：先用较短 MP4 测试，再评估香港线路；不是购买更贵域名可以解决的问题。
- MOV/HEVC 不播放：浏览器编码支持不同，转成 H.264 视频 + AAC 音频的 MP4。应用不自动转码，只生成封面。
- HEIC：首版不支持，请导出为 JPG 再上传。
- 登录输错过多：等 15 分钟。首版仅两人使用，限速按代理连接 IP 共享计数。

## 本地开发

需要 Python 3.12、Node.js 20+，以及 ffmpeg/ffprobe（视频校验和封面依赖）。

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell 则使用 .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/setup.py
uvicorn app.main:app --reload
```

打开 **http://localhost:8000**，不要换成 `127.0.0.1`，否则需同步设置 `PUBLIC_URL`。

前端已经构建好，直接运行后端即可。修改 React 源码后：

```bash
npm ci
npm run build
```

前端入口为 `frontend.jsx`；样式在 `app/static/style.css`；后端在 `app/main.py`。无需注册 OAuth、微信开放平台或第三方数据库。

测试（测试库在临时目录，不影响实际记录）：

```bash
pip install pytest httpx
python -m pytest tests -q
```

## 备份、恢复与数据容量

**服务器磁盘不是独立备份。** 视频会占用空间，并消耗套餐流量。初版单文件上限 100 MB、每次合计 200 MB、最多 12 个附件；建议先上传短视频。按需求升级 COS 时需同时实现鉴权，不能简单把存储桶改成公开。

全量备份（会短暂停止应用，结束后自动启动）：

```bash
sh scripts/backup.sh
```

将 `backups/` 中的压缩包下载到自己的电脑或独立存储。包内含照片原文件、视频、缩略图、记录、账号密码哈希与会话，需私密保存。建议每周至少执行一次，或用自己服务器的定时任务调度脚本。当前交付没有替你开通任何定时任务。

首页“导出文字与记录清单”只有 JSON 和媒体相对链接，**不包含照片视频文件**，不能代替全量备份。

恢复到同样的应用目录时：先停止服务，为当前 `data/` 做备份并移走，再将备份包解压到应用根目录，使目录结构恢复为 `data/blue.db` 和 `data/media/`，然后 `docker compose up -d`。不要将旧备份直接覆盖混入一个正在运行的库。

升级前备份。不要删除 `data/`；不要将数据库、备份、`.env` 提交到 Git。

## 版本边界

- 一个固定双人空间，无公开注册、邀请系统或多人空间。
- 支持发布和删除，暂未提供编辑、回收站、找回密码、对象存储迁移和视频转码。
- 原始照片可能含拍摄位置等 EXIF；缩略图重编码。当前访问控制不是端到端加密，服务器管理员可以读取文件。
- 全年图保留照片缩略图和蓝色热度，手机上可横向滚动；月历默认优先显示照片。
- 没有内置收费或第三方统计，不调用 AI 服务。

## 官方参考

- 腾讯云轻量服务器地域与网络：https://cloud.tencent.com/document/product/1207/50103
- 腾讯云备案要求：https://cloud.tencent.com/document/api/243/19630
- Docker Ubuntu 安装：https://docs.docker.com/engine/install/ubuntu/
- Caddy HTTPS：https://caddyserver.com/docs/automatic-https
- FastAPI 文件上传：https://fastapi.tiangolo.com/tutorial/request-files/
