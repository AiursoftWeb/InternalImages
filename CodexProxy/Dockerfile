FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal:latest

# 系统依赖安装（curl 供 uv 安装脚本 + 健康检查使用；git 用于拉取源码）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    # uv 独立安装的 Python 放到 /opt 而不是默认的 ~/.local（/root 下），
    # 否则后面切到非 root 用户运行时，因为 /root 目录权限(700)
    # 会读不到解释器，导致容器启动失败。
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# 创建并使用虚拟环境（锁定 Python 3.13；codex-proxy 要求 >=3.11）
RUN uv python install 3.13 \
    && uv venv --python 3.13 /opt/venv \
    && chmod -R a+rX /opt/uv-python
ENV PATH="/opt/venv/bin:${PATH}"

# 拉取 codex-proxy 源码并安装。
# 锁定到具体 commit 而不是浮动的 main 分支，保证可复现构建；
# 该仓库目前没有打 tag/发过 Release，main 是唯一来源，
# 但为了不让每次 build 都拉到不同代码，这里默认钉在下面这个 commit，
# 需要跟新代码时手动更新 CODEX_PROXY_REF（或显式传 --build-arg）。
ARG CODEX_PROXY_REPO=https://gitlab.aiursoft.com/ZeTian/codex-proxy.git
ARG CODEX_PROXY_REF=a6dd9e90bd7747eb0508c7a2d959cc49e32ffa07
RUN git clone --filter=blob:none "${CODEX_PROXY_REPO}" /tmp/codex-proxy \
    && git -C /tmp/codex-proxy checkout "${CODEX_PROXY_REF}" \
    && uv pip install /tmp/codex-proxy \
    && rm -rf /tmp/codex-proxy

# 启动适配层：把宿主机 Codex CLI 的 auth.json 首次导入为
# codex-proxy 自己的 credentials.json，之后交给它自己刷新 token。
COPY import_auth.py /usr/local/bin/import_auth.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY sitecustomize.py /opt/codex-proxy-patches/sitecustomize.py
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONPATH=/opt/codex-proxy-patches \
    CODEX_PROXY_PORT=8787 \
    CODEX_PROXY_HOST=0.0.0.0 \
    CODEX_HOME=/home/appuser/.codex \
    CODEX_AUTH_JSON=/home/appuser/.codex/auth.json \
    HOME=/home/appuser

RUN useradd --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && mkdir -p /home/appuser/.codex-proxy /home/appuser/.codex \
    && chown -R appuser:appuser /home/appuser /opt/venv

USER appuser
WORKDIR /home/appuser

# 持久化卷：codex-proxy 自己维护/刷新的 token 存储，
# 不做持久化的话每次重建容器都会重新触发一次 auth.json 导入。
VOLUME ["/home/appuser/.codex-proxy"]

EXPOSE 8787

ENTRYPOINT ["docker-entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8787/health || exit 1
