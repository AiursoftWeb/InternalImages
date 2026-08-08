FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD "https://api.github.com/repos/JingyunLiang/SwinIR/commits?per_page=1" latest_commit
RUN git clone --depth 1 https://github.com/JingyunLiang/SwinIR.git

ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir opencv-python torch torchvision requests numpy timm

# Download the model
RUN mkdir -p model_zoo/swinir && \
    wget -O model_zoo/swinir/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth

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
