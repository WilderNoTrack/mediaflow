# MediaFlow 在线版镜像：前端打包 + 后端运行，一个容器一个进程（任务队列在进程内，不要开多副本/多 worker）。
# 国内服务器默认走 npmmirror / 阿里云 PyPI；基础镜像拉不下来时用 --build-arg 换成国内镜像站，见 DEPLOY.md。
ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS web
ARG NPM_REGISTRY=https://registry.npmmirror.com
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm config set registry "$NPM_REGISTRY" && npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai
WORKDIR /app/server
COPY server/pyproject.toml server/alembic.ini ./
COPY server/mediaflow ./mediaflow
COPY server/migrations ./migrations
RUN pip install -i "$PIP_INDEX_URL" -e .
COPY --from=web /app/web/dist /app/web/dist
# 数据（数据库、图片、平台登录态、Key）都在 /data，挂卷持久化
ENV MEDIAFLOW_DATA_DIR=/data \
    MEDIAFLOW_HOST=0.0.0.0 \
    MEDIAFLOW_PORT=8765 \
    MEDIAFLOW_OPEN_BROWSER=false \
    FORWARDED_ALLOW_IPS=*
VOLUME /data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)" || exit 1
CMD ["mediaflow", "--no-browser"]
