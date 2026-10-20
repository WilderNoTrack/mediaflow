# MediaFlow 在线版部署指南

> 写给负责部署的人或 AI agent。目标：把 MediaFlow 部署到一台**国内云服务器**（2 核 2G 够用），用域名 + HTTPS 访问。现阶段用**演示版**：打开网址就能用，不用注册登录。

## 0. 先了解这几件事

- **三种模式**（`MEDIAFLOW_AUTH`）：
  - `demo` **演示版（现在用这个）**：谁打开网址都能直接用，大家看到同一份账号和草稿。Key、平台连接这些设置被锁住，访客看不到入口；管理员打开 `/admin` 输入 `MEDIAFLOW_ADMIN_TOKEN` 后，这个浏览器就能改（记住 30 天）。每天的写稿 / 对话次数是**全站共用的总额度**，用来兜住 Key 的花费。
  - `password` 登录版：管理员在「成员管理」里给每人开账号，数据按人隔离，每人有额度。以后正式给人用时再切过去，见第 8 节。
  - 不设 = 本地版（自己电脑上用，不要直接暴露到公网：谁都能改设置）。
- **管理员提供一切：** DeepSeek Key、生图 Key、小红书等平台的登录态都由管理员配一次，所有人共用。
- **只能跑一个进程。** 后台任务队列在进程里：不要开多个 worker、多个容器副本，也不要用 gunicorn 多进程。
- **数据全在一个目录**（Docker 是 `./data`，裸机是 `/var/lib/mediaflow`）：SQLite 数据库、图片、平台登录态、页面里填的 Key。备份它就是备份全部。
- **国内服务器 + 域名走 80/443 必须先完成 ICP 备案**，否则会被云厂商拦截。备案下来前可以先用 `http://服务器IP:8765` 内测（见 3.4），但这是明文 HTTP，只适合短期测试。
- 推荐系统：Ubuntu 22.04 / 24.04（下文命令以 Ubuntu 为准）。

## 1. 准备

1. 云厂商控制台 → 安全组放行 **80、443**（测试阶段再放 8765）。
2. 域名 DNS 加一条 **A 记录** 指向服务器公网 IP，例如 `mf.example.com`。
3. 内存只有 2G 时先加 2G swap，避免构建前端时被 OOM：
   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
4. 拿代码（仓库是私有的话需要 GitHub token 或 deploy key；GitHub 在国内不稳定，clone 失败就重试，或在别处打包后 scp 上来）：
   ```bash
   sudo git clone -b v2 https://github.com/WilderNoTrack/mediaflow.git /opt/mediaflow
   ```
5. 生成配置：
   ```bash
   cd /opt/mediaflow
   cp deploy/online.env.example deploy/online.env && chmod 600 deploy/online.env
   openssl rand -hex 16     # 填到 MEDIAFLOW_ADMIN_TOKEN
   ```
   演示版必填：`MEDIAFLOW_AUTH=demo`、`MEDIAFLOW_ADMIN_TOKEN`（用 `openssl rand -hex 16` 生成，交给管理员保管）；Docker 方式还要填 `DOMAIN`。按预算调 `MEDIAFLOW_DAILY_WRITES` / `MEDIAFLOW_DAILY_CHATS`（全站每天总量）。Key 可以留空，上线后在页面里填。

## 2. 方式 A：Docker（推荐，最省事）

### 2.1 装 Docker（国内）

```bash
curl -fsSL https://get.docker.com | sudo sh -s -- --mirror Aliyun
```

Docker Hub 在国内基本拉不动，给 Docker 配镜像加速（阿里云控制台「容器镜像服务 → 镜像加速器」有你的专属地址，或用可用的公共加速站）：

```bash
sudo mkdir -p /etc/docker
echo '{ "registry-mirrors": ["https://<你的加速地址>"] }' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

加速站也不好用时，可以直接把基础镜像换成国内镜像站的完整地址（写进 `/opt/mediaflow/.env`，compose 会读）：

```bash
NODE_IMAGE=docker.m.daocloud.io/library/node:20-alpine
PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
CADDY_IMAGE=docker.m.daocloud.io/library/caddy:2-alpine
```

npm、pip 默认已经走 npmmirror 和阿里云 PyPI（见 `Dockerfile` 的 `NPM_REGISTRY`、`PIP_INDEX_URL`）。

### 2.2 启动

```bash
cd /opt/mediaflow
sudo docker compose up -d --build
sudo docker compose logs -f app      # 看到 “MediaFlow 已启动” 就好了
```

Caddy 会自动给 `DOMAIN` 申请 HTTPS 证书（需要 80/443 能从公网访问、DNS 已生效、已备案）。打开 `https://你的域名` 即可。

### 2.3 日常

| 做什么 | 命令 |
|---|---|
| 更新版本 | `git pull && sudo docker compose up -d --build` |
| 看日志 | `sudo docker compose logs -f --tail 200 app` |
| 重启 | `sudo docker compose restart app` |
| 改管理员口令 | 改 `deploy/online.env` 里的 `MEDIAFLOW_ADMIN_TOKEN`，然后 `sudo docker compose up -d`（旧口令解锁过的浏览器全部失效） |
| 备份 | 见第 5 节，数据在 `/opt/mediaflow/data` |

## 3. 方式 B：不用 Docker（systemd + nginx）

### 3.1 装运行环境

需要 Python ≥ 3.11、Node ≥ 18（只在构建前端时用）。

```bash
sudo apt update
# Ubuntu 24.04 自带 python3.12；22.04 用 python3.11
sudo apt install -y python3.12 python3.12-venv nginx || sudo apt install -y python3.11 python3.11-venv nginx
# Node 从 npmmirror 下载（官方源在国内很慢）
curl -fsSL https://registry.npmmirror.com/-/binary/node/v20.18.0/node-v20.18.0-linux-x64.tar.xz | sudo tar -xJ -C /opt
sudo ln -sf /opt/node-v20.18.0-linux-x64/bin/{node,npm,npx} /usr/local/bin/
```

### 3.2 构建和安装

```bash
cd /opt/mediaflow/web
npm config set registry https://registry.npmmirror.com
npm ci && npm run build                       # 产物在 web/dist，后端会自动托管

cd /opt/mediaflow/server
python3.12 -m venv .venv                      # 22.04 用 python3.11
.venv/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ -e .
```

### 3.3 配置并启动服务

```bash
sudo useradd --system --home /var/lib/mediaflow --shell /usr/sbin/nologin mediaflow
sudo mkdir -p /var/lib/mediaflow /etc/mediaflow
sudo chown mediaflow:mediaflow /var/lib/mediaflow
sudo cp /opt/mediaflow/deploy/online.env /etc/mediaflow/mediaflow.env
sudo chown root:mediaflow /etc/mediaflow/mediaflow.env && sudo chmod 640 /etc/mediaflow/mediaflow.env
sudo cp /opt/mediaflow/deploy/mediaflow.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mediaflow
sudo journalctl -u mediaflow -f                # 看到 “MediaFlow 已启动” 就好了
curl -s http://127.0.0.1:8765/health
```

### 3.4 反向代理和 HTTPS

- nginx：参考 `deploy/nginx.conf`，换成你的域名和证书路径（云厂商可免费申请 DV 证书，或用 certbot / acme.sh），然后 `sudo nginx -t && sudo systemctl reload nginx`。**`X-Forwarded-Proto` 那行必须保留**，登录 Cookie 靠它判断 HTTPS；`chat/stream` 那段（关掉缓冲）也要保留，不然和小媒对话的回复会憋到最后才一下子出来。
- 也可以用 Caddy 代替 nginx：照 `deploy/Caddyfile` 写，把 `app:8765` 换成 `127.0.0.1:8765`，证书全自动。
- 备案下来前想先内测：把 `mediaflow.service` 里的 `--host 127.0.0.1` 改成 `--host 0.0.0.0`，安全组放行 8765，用 `http://服务器IP:8765` 访问。备案后改回去。

### 3.5 日常

| 做什么 | 命令 |
|---|---|
| 更新版本 | `cd /opt/mediaflow && git pull && (cd web && npm ci && npm run build) && server/.venv/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ -e server && sudo systemctl restart mediaflow` |
| 看日志 | `sudo journalctl -u mediaflow -f` |

改管理员口令：改 `/etc/mediaflow/mediaflow.env` 里的 `MEDIAFLOW_ADMIN_TOKEN` 后 `sudo systemctl restart mediaflow`。

数据库结构升级是自动的（启动时迁移），更新前先备份即可。

## 4. 上线后，管理员要做的事

1. 打开 `https://你的域名/admin`，输入 `MEDIAFLOW_ADMIN_TOKEN`。页面上没有这个入口的链接，口令别发给访客。
2. 回首页，「开始之前」里：
   - 填 **DeepSeek Key**（必需，没有它写稿和对话都用不了；保存前会实测一次）。
   - **AI 配图**：填生图 Key（可选，不填就没有配图）。
   - **连接平台**：用小红书**小号**扫码登录（找对标博主、读作品都靠它）。所有访客共用这个登录态，用的人多时请求都压在这一个号上，有被平台限流的风险；被要求重新登录时再扫一次即可。
3. 把网址发给要看演示的人就行。右上角「演示版」能看到今天全站还剩多少额度；用完了当天就写不了，第二天 0 点（北京时间）恢复。
4. 演示版大家能互相看到、修改、删除账号和草稿：提醒大家别放隐私信息，重要的演示数据记得备份（第 5 节）。

> 从本地版迁过来：把本地的数据目录（默认 `server/data/`）整个拷到服务器的数据目录再启动，原来的账号和草稿都在。

## 5. 备份

SQLite 开着 WAL，直接 cp 正在写的库可能不完整。用在线备份：

```bash
# Docker：DATA=/opt/mediaflow/data   裸机：DATA=/var/lib/mediaflow
DATA=/opt/mediaflow/data; DEST=/root/mediaflow-backup/$(date +%F); sudo mkdir -p "$DEST"
sudo python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" "$DATA/mediaflow.db" "$DEST/mediaflow.db"
sudo rsync -a --exclude 'mediaflow.db*' "$DATA/" "$DEST/"
```

可以放进 crontab 每天跑一次，并定期拷到服务器之外（对象存储等）。数据目录里有 Key 和平台登录态，备份也要妥善保管。

## 6. 安全清单

- `deploy/online.env` / `/etc/mediaflow/mediaflow.env` 权限 600/640，**不要提交到 git**（已在 `.gitignore`）。
- 只对公网开放 80/443；8765 只在内测阶段临时开放。
- 演示版：管理员口令连续输错 5 次会锁 10 分钟；口令只给自己，泄露了就换一个并重启。
- 演示版靠全站每日额度控制花费，按 Key 的预算设 `MEDIAFLOW_DAILY_WRITES` / `MEDIAFLOW_DAILY_CHATS`，不要设成 0（不限）。
- 怀疑 Key 泄露：去 DeepSeek / 生图平台后台作废旧 Key，用管理员账号在页面里换新 Key。

## 7. 常见问题

- **打开是 502**：后端没起来，看日志。登录版最常见的是缺 `MEDIAFLOW_SECRET` 或首次启动缺 `MEDIAFLOW_ADMIN_PASSWORD`。
- **HTTPS 证书申请失败**：DNS 没生效、80 端口没放行、或域名未备案被拦截。
- **/admin 输对了口令，回首页还是看不到设置**：用 HTTP 访问却经过了把 `X-Forwarded-Proto` 设成 https 的代理（Cookie 带了 Secure 存不下）。检查反代配置。
- **登录版：登录后马上又回到登录页**：用 HTTP 访问却经过了把 `X-Forwarded-Proto` 设成 https 的代理，或者改过 `MEDIAFLOW_SECRET`。检查反代配置后清浏览器 Cookie 重试。
- **构建时被 kill / 卡住**：内存不够，按 1.3 加 swap。
- **访客提示“管理员还没配好模型”**：管理员去 `/admin` 解锁后在首页填 DeepSeek Key。

## 8. 以后切到登录版（每人一个账号）

在配置里改成 `MEDIAFLOW_AUTH=password`，并填 `MEDIAFLOW_SECRET`（`openssl rand -hex 32`）、`MEDIAFLOW_ADMIN_USER`、`MEDIAFLOW_ADMIN_PASSWORD`（≥8 位），重启。

- 打开网址先登录；不开放注册，管理员在右上角「成员管理」里开账号，把弹出来的网址、用户名、密码发给对方，也能重置密码、停用、看用量。
- 每人的账号和草稿互相隔离；演示版期间产生的数据会归到管理员名下。
- `MEDIAFLOW_DAILY_WRITES` / `MEDIAFLOW_DAILY_CHATS` 变成**每个成员**每天的量（管理员不限）。
- 同一用户名连续输错 5 次密码锁 10 分钟；停用或重置密码后，对方已有的登录立即失效。
- 忘了管理员密码：Docker 用 `sudo docker compose exec app mediaflow reset-password admin`；裸机用
  `sudo -u mediaflow bash -c 'set -a; . /etc/mediaflow/mediaflow.env; export MEDIAFLOW_DATA_DIR=/var/lib/mediaflow; /opt/mediaflow/server/.venv/bin/mediaflow reset-password admin'`。
