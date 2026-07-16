FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ASR_REALTIME_PORT=10095 \
    ASR_REALTIME_DEVICE=cpu \
    ASR_REALTIME_NGPU=0 \
    ASR_REALTIME_NCPU=4

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio

RUN pip install "funasr==1.3.14" "modelscope==1.38.1" "websockets==12.0" "scipy==1.15.3"

COPY server.py /app/server.py

EXPOSE 10095

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${ASR_REALTIME_PORT:-10095} --device ${ASR_REALTIME_DEVICE:-cpu} --ngpu ${ASR_REALTIME_NGPU:-0} --ncpu ${ASR_REALTIME_NCPU:-4} --certfile ''"]
