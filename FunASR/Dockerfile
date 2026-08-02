FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ARG USE_PYPI_MIRROR=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    FUNASR_MODEL=sensevoice \
    FUNASR_DEVICE=cuda \
    FUNASR_PORT=8000 \
    CUDA_VISIBLE_DEVICES=0 \
    MODELSCOPE_CACHE=/root/.cache/modelscope \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends aria2 ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pytorch-cu124-wheels.txt /tmp/pytorch-cu124-wheels.txt
RUN mkdir -p /tmp/pytorch-wheels \
    && aria2c --auto-file-renaming=false --continue=true --input-file=/tmp/pytorch-cu124-wheels.txt \
        --dir=/tmp/pytorch-wheels --max-concurrent-downloads=4 --max-connection-per-server=8 \
        --max-tries=10 --min-split-size=1M --retry-wait=5 --split=8 \
    && pip install --no-index --find-links=/tmp/pytorch-wheels \
        "torch==2.6.0+cu124" "torchaudio==2.6.0+cu124" \
    && rm -r /tmp/pytorch-wheels \
    && rm /tmp/pytorch-cu124-wheels.txt
RUN if [ "$USE_PYPI_MIRROR" = "true" ]; then \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple; \
    else \
        PIP_INDEX_URL=https://pypi.org/simple; \
    fi \
    && pip install --index-url "$PIP_INDEX_URL" funasr fastapi "uvicorn[standard]" python-multipart huggingface_hub

# Bake models into the image at build time (CPU-only download) so they are
# not fetched at runtime; server.py reloads them onto the GPU via --device cuda.
COPY bake_models.py /app/bake_models.py
RUN python bake_models.py

COPY server.py /app/server.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; request = urllib.request.Request('http://127.0.0.1:%s/health' % os.getenv('FUNASR_PORT', '8000'), headers={'Authorization': 'Bearer ' + os.environ['ASR_FUNASR_TOKEN']}); urllib.request.urlopen(request, timeout=3).read()" || exit 1

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${FUNASR_PORT:-8000} --device ${FUNASR_DEVICE:-cuda} --model ${FUNASR_MODEL:-sensevoice}"]
