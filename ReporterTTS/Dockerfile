FROM hub.aiursoft.cn/aiursoft/internalimages/nvidia:latest

# 必要包：clickhouse-connect 做写入；tzdata 提供时区；watchdog/uvloop 可选
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tzdata python3 python-is-python3 python3-pip ffmpeg git curl wget \
        build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# 【删除这一行】
# RUN pip install clickhouse-connect==0.8.18 uvloop==0.21.0 watchdog==6.0.0

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
WORKDIR /app

ADD "https://api.github.com/repos/index-tts/index-tts/commits?per_page=1" latest_commit
RUN git clone https://github.com/index-tts/index-tts.git

WORKDIR /app/index-tts

# 【修改这一段 RUN 命令】
# 将所有依赖项统一用 uv 安装到虚拟环境中
RUN . "$HOME/.local/bin/env" \
	&& uv --version \
	&& uv venv tts \
	&& . "tts/bin/activate" \
	&& uv pip install uvicorn fastapi clickhouse-connect uvloop \
	&& uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118 \
	&& uv pip install -e .

RUN . "$HOME/.local/bin/env" \
	&& . "tts/bin/activate" \
	&& hf download IndexTeam/IndexTTS-1.5 config.yaml bigvgan_discriminator.pth bigvgan_generator.pth bpe.model dvae.pth gpt.pth unigram_12000.vocab --local-dir checkpoints

COPY . .

# 默认环境变量（可在 compose/Swarm 覆盖）
ENV CLICKHOUSE_URL=http://clickhouse:8123 \
    CLICKHOUSE_USER=default \
    CLICKHOUSE_PASSWORD=123456 \
    CLICKHOUSE_DATABASE=logs \
    CLICKHOUSE_TABLE=caddy_requests \
    BATCH_SIZE=1000 \
    FLUSH_INTERVAL_SEC=2 \
    TZ="UTC"

EXPOSE 8000
CMD ["/app/index-tts/tts/bin/uvicorn","main:app","--host","0.0.0.0","--port", "8000"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=3 \
  CMD curl --fail http://localhost:8000/health || exit 1
