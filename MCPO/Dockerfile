FROM hub.aiursoft.com/ghcr.io/open-webui/mcpo:main

# AnyIO 4.14.2 fixes cancellation delivery spinning after MCP connection failures.
RUN uv pip install --python /app/.venv/bin/python 'anyio>=4.14.2,<5' \
    && uv pip check --python /app/.venv/bin/python
