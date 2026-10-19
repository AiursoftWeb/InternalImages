FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal:latest

# curl is used by the uv installer and the health check.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
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

# Build from the checked-in source, including the existing request-size fix.
COPY source/ /tmp/codex-proxy/
RUN uv pip install /tmp/codex-proxy \
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
    CODEX_PROXY_CLIENT_MAX_SIZE_MIB=64 \
    CODEX_HOME=/home/appuser/.codex \
    CODEX_AUTH_JSON=/home/appuser/.codex/auth.json \
    HOME=/home/appuser

# Guard against silently regressing to aiohttp's 1 MiB default when the
# upstream project or its application factory changes.
RUN python -c "from codex_proxy.server import create_app; assert create_app()._client_max_size == 64 * 1024 * 1024" \
    && CODEX_PROXY_CLIENT_MAX_SIZE_MIB=32 python -c "from codex_proxy.server import create_app; assert create_app()._client_max_size == 32 * 1024 * 1024"

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
