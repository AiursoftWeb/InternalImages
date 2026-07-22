FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ARG SINGLE_MODEL=false
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
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --index-url https://download.pytorch.org/whl/cu124 "torch==2.6.0" "torchaudio==2.6.0"
RUN pip install "fastapi==0.116.1" "uvicorn[standard]==0.35.0" "python-multipart==0.0.20" "whisperx==3.8.6"

# Bake the curated WhisperX model levels (models_config.BAKED_MODELS) into the
# image at build time so ops can switch offline. Edit BAKED_MODELS and rebuild
# to change the offline-available set. device='cpu' only triggers the download;
# the cached weights are device-agnostic and app.py reloads them onto the GPU
# (WHISPERX_DEVICE=cuda) at runtime. The default is large-v3, which fits
# comfortably on one RTX 3090 (24G) leaving headroom for other services.
COPY models_config.py bake_models.py /app/
RUN python bake_models.py

COPY app.py /app/app.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5m --retries=3 CMD python -c "import os, urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/health', headers={'Authorization': 'Bearer ' + os.environ['ASR_WHISPERX_TOKEN']}); urllib.request.urlopen(request, timeout=3).read()" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
