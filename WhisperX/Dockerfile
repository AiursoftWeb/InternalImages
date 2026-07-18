FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    WHISPERX_DEVICE=cuda \
    WHISPERX_COMPUTE_TYPE=float16 \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --index-url https://download.pytorch.org/whl/cu124 torch torchaudio
RUN pip install "fastapi==0.116.1" "uvicorn[standard]==0.35.0" "python-multipart==0.0.20" "whisperx==3.8.6"

# Bake the default whisper model into the image at build time. device='cpu'
# only triggers the download; the cached weights are device-agnostic and
# app.py reloads them onto the GPU via WHISPERX_DEVICE=cuda at runtime.
RUN python -c "import whisperx; whisperx.load_model('small', device='cpu')"

COPY app.py /app/app.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5m --retries=3 CMD python -c "import os, urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/health', headers={'Authorization': 'Bearer ' + os.environ['ASR_WHISPERX_TOKEN']}); urllib.request.urlopen(request, timeout=3).read()" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
