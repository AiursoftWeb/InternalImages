FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends aria2 git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Retry the entire download: aria2 does not retry every TLS failure internally.
COPY --chmod=755 <<'EOF' /usr/local/bin/download
#!/bin/sh
for attempt in 1 2 3 4 5; do
    aria2c --continue=true --max-connection-per-server=8 --split=8 --min-split-size=1M \
        --max-tries=1 --connect-timeout=20 --timeout=60 --lowest-speed-limit=16K \
        --auto-file-renaming=false --check-integrity=true "$@" && exit 0
    status=$?
    [ "$attempt" -eq 5 ] && exit "$status"
    sleep 5
done
EOF

ADD "https://api.github.com/repos/JingyunLiang/SwinIR/commits?per_page=1" latest_commit
RUN git clone --depth 1 https://github.com/JingyunLiang/SwinIR.git

ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_RETRIES=4 \
    PIP_TIMEOUT=60

RUN <<'SH'
set -eu
# Use a temporary pip 25.3+ resolver without replacing the distribution-managed pip.
python3 -m pip install --target /tmp/build-pip 'pip>=25.3'
export PYTHONPATH=/tmp/build-pip
packages='opencv-python torch torchvision requests numpy timm'
python3 -m pip install --dry-run --only-binary=:all: --report /tmp/packages.json $packages
python3 - <<'PY'
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

with open('/tmp/packages.json') as report, open('/tmp/packages.aria2', 'w') as downloads:
    for package in json.load(report)['install']:
        info = package['download_info']
        filename = Path(unquote(urlsplit(info['url']).path)).name
        checksum = info['archive_info']['hashes']['sha256']
        downloads.write(f"{info['url']}\n out={filename}\n checksum=sha-256={checksum}\n")
PY
download --input-file=/tmp/packages.aria2 --dir=/tmp/wheels --max-concurrent-downloads=4
python3 -m pip install --no-index --find-links=/tmp/wheels $packages
rm -rf /tmp/build-pip /tmp/packages.json /tmp/packages.aria2 /tmp/wheels
SH

# Download the model
RUN mkdir -p model_zoo/swinir && \
    download --dir=model_zoo/swinir --out=003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth

RUN mkdir -p /app/input
RUN mkdir -p /app/results/swinir_real_sr_x4_large

VOLUME /app/input
VOLUME /app/results/swinir_real_sr_x4_large

ENV SCALE=4
ENV TILE=192
ENV TILE_OVERLAP=16

ENTRYPOINT ["bash", "-c", "python3 ./SwinIR/main_test_swinir.py --task real_sr --scale ${SCALE} --large_model --model_path model_zoo/swinir/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth --folder_lq /app/input --tile ${TILE} --tile_overlap ${TILE_OVERLAP}"]
# Usage
# Prepare two folders: input and output
#sudo docker run --gpus all -it -v $(pwd)/input:/app/input -v $(pwd)/output:/app/results/swinir_real_sr_x4_large tagname
