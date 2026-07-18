FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    ASR_REALTIME_PORT=10095 \
    ASR_REALTIME_DEVICE=cuda \
    ASR_REALTIME_NGPU=1 \
    ASR_REALTIME_NCPU=4 \
    MODELSCOPE_CACHE=/root/.cache/modelscope

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --index-url https://download.pytorch.org/whl/cu124 torch torchaudio
RUN pip install "funasr==1.3.14" "modelscope==1.38.1" "websockets==12.0" "scipy==1.15.3"

# Bake models into the image so they are not downloaded at runtime.
COPY bake_models.py /app/bake_models.py
RUN ASR_REALTIME_TOKEN=dummy python bake_models.py

COPY server.py /app/server.py

EXPOSE 10095

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${ASR_REALTIME_PORT:-10095} --device ${ASR_REALTIME_DEVICE:-cuda} --ngpu ${ASR_REALTIME_NGPU:-1} --ncpu ${ASR_REALTIME_NCPU:-4} --certfile ''"]
