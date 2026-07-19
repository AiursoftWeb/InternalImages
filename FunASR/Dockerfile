FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

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
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --index-url https://download.pytorch.org/whl/cu124 "torch==2.6.0" "torchaudio==2.6.0"
RUN pip install funasr fastapi "uvicorn[standard]" python-multipart huggingface_hub

# Bake models into the image at build time (CPU-only download) so they are
# not fetched at runtime; server.py reloads them onto the GPU via --device cuda.
COPY bake_models.py /app/bake_models.py
RUN python bake_models.py

COPY server.py /app/server.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; request = urllib.request.Request('http://127.0.0.1:%s/health' % os.getenv('FUNASR_PORT', '8000'), headers={'Authorization': 'Bearer ' + os.environ['ASR_FUNASR_TOKEN']}); urllib.request.urlopen(request, timeout=3).read()" || exit 1

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${FUNASR_PORT:-8000} --device ${FUNASR_DEVICE:-cuda} --model ${FUNASR_MODEL:-sensevoice}"]
