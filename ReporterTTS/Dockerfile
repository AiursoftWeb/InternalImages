FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tzdata python3 python-is-python3 python3-pip ffmpeg git wget \
        build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
WORKDIR /app

ADD "https://api.github.com/repos/index-tts/index-tts/commits?per_page=1" latest_commit
RUN git clone https://git.aiursoft.com/PublicVault/index-tts.git

WORKDIR /app/index-tts

RUN . "$HOME/.local/bin/env" \
	&& uv --version \
	&& uv venv tts \
	&& . "tts/bin/activate" \
	&& uv pip install uvicorn fastapi python-multipart \
	&& if [ "$(uname -m)" = "x86_64" ]; then \
		uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126; \
	else \
		uv pip install torch torchaudio; \
	fi \
	&& uv pip install -e .

RUN . "$HOME/.local/bin/env" \
	&& . "tts/bin/activate" \
	&& hf download IndexTeam/IndexTTS-1.5 config.yaml bigvgan_discriminator.pth bigvgan_generator.pth bpe.model dvae.pth gpt.pth unigram_12000.vocab --local-dir checkpoints

COPY . .

VOLUME /data

ENV DATA_DIR=/data \
    TZ="UTC"

EXPOSE 8000
CMD ["/app/index-tts/tts/bin/uvicorn","main:app","--host","0.0.0.0","--port", "8000"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=3 \
  CMD curl --fail http://localhost:8000/health || exit 1
