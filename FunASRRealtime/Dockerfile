FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

ARG USE_PYPI_MIRROR=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    ASR_REALTIME_PORT=10095 \
    ASR_REALTIME_DEVICE=cuda \
    ASR_REALTIME_NGPU=1 \
    ASR_REALTIME_NCPU=4 \
    CUDA_VISIBLE_DEVICES=0 \
    MODELSCOPE_CACHE=/root/.cache/modelscope

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends aria2 ffmpeg libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN aria2c --continue=true --max-connection-per-server=16 --max-tries=10 --min-split-size=1M --retry-wait=5 --split=16 \
        --dir=/tmp --out=torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl \
        "https://download-r2.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp312-cp312-linux_x86_64.whl" \
    && echo "a393b506844035c0dac2f30ea8478c343b8e95a429f06f3b3cadfc7f53adb597  /tmp/torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl" | sha256sum --check \
    && aria2c --continue=true --max-connection-per-server=16 --max-tries=10 --min-split-size=1M --retry-wait=5 --split=16 \
        --dir=/tmp --out=torchaudio-2.6.0+cu124-cp312-cp312-linux_x86_64.whl \
        "https://download-r2.pytorch.org/whl/cu124/torchaudio-2.6.0%2Bcu124-cp312-cp312-linux_x86_64.whl" \
    && echo "3e5ffa69606171c74f3e2b969785ead50b782ca657e746aaee1ee7cc88dcfc08  /tmp/torchaudio-2.6.0+cu124-cp312-cp312-linux_x86_64.whl" | sha256sum --check \
    && pip install --timeout 600 --retries 10 --index-url https://download.pytorch.org/whl/cu124 \
        /tmp/torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl \
        /tmp/torchaudio-2.6.0+cu124-cp312-cp312-linux_x86_64.whl \
    && rm /tmp/torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl \
        /tmp/torchaudio-2.6.0+cu124-cp312-cp312-linux_x86_64.whl
RUN if [ "$USE_PYPI_MIRROR" = "true" ]; then \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple; \
    else \
        PIP_INDEX_URL=https://pypi.org/simple; \
    fi \
    && pip install --index-url "$PIP_INDEX_URL" "funasr==1.3.14" "modelscope==1.38.1" "websockets==12.0" "scipy==1.15.3"

# Bake models into the image at build time (CPU-only download) so they are
# not fetched at runtime; server.py reloads them onto the GPU via --device cuda.
# Model selection entry point: override ASR_REALTIME_ASR_MODEL,
# ASR_REALTIME_ASR_MODEL_ONLINE, ASR_REALTIME_VAD_MODEL, ASR_REALTIME_PUNC_MODEL
# or ASR_REALTIME_SV_MODEL at runtime to swap models (unbaked models download
# on first use). Defaults below are the models baked during build.
COPY bake_models.py /app/bake_models.py
RUN ASR_REALTIME_TOKEN=dummy python bake_models.py

COPY server.py /app/server.py

EXPOSE 10095

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${ASR_REALTIME_PORT:-10095} --device ${ASR_REALTIME_DEVICE:-cuda} --ngpu ${ASR_REALTIME_NGPU:-1} --ncpu ${ASR_REALTIME_NCPU:-4} --certfile ''"]
