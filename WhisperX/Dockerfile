FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ARG SINGLE_MODEL=true
ARG USE_PYPI_MIRROR=false
ENV SINGLE_MODEL=${SINGLE_MODEL}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    WHISPERX_MODEL=large-v3 \
    WHISPERX_DEVICE=cuda \
    WHISPERX_COMPUTE_TYPE=float16 \
    CUDA_VISIBLE_DEVICES=0 \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends aria2 ffmpeg \
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
    && pip install --index-url "$PIP_INDEX_URL" "fastapi==0.116.1" "uvicorn[standard]==0.35.0" "python-multipart==0.0.20" "whisperx==3.8.6"

# Bake the curated WhisperX model levels (models_config.BAKED_MODELS) into the
# image at build time so ops can switch offline. Edit BAKED_MODELS and rebuild
# to change the offline-available set. device='cpu' only triggers the download;
# the cached weights are device-agnostic and app.py reloads them onto the GPU
# (WHISPERX_DEVICE=cuda) at runtime. The default is large-v3, which fits
# comfortably on one RTX 3090 (24G) leaving headroom for other services.
COPY models_config.py bake_models.py /app/
RUN python bake_models.py

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY app.py /app/app.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5m --retries=3 CMD python -c "import os, urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/health', headers={'Authorization': 'Bearer ' + os.environ['ASR_WHISPERX_TOKEN']}); urllib.request.urlopen(request, timeout=3).read()" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
