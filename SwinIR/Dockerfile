FROM hub.aiursoft.cn/aiursoft/internalimages/nvidia:latest
WORKDIR /app
RUN sudo apt update && sudo apt install -y git
RUN git clone https://github.com/JingyunLiang/SwinIR.git

RUN pip install opencv-python torch torchvision
RUN pip install requests numpy timm

# Download the model
RUN mkdir -p model_zoo/swinir && \
    wget -O model_zoo/swinir/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth

RUN mkdir -p /app/input
RUN mkdir -p /app/results/swinir_real_sr_x4_large

VOLUME /app/input
VOLUME /app/results/swinir_real_sr_x4_large

ENTRYPOINT ["python3", "./SwinIR/main_test_swinir.py", "--task", "real_sr", "--scale", "2", "--large_model", "--model_path", "model_zoo/swinir/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth", "--folder_lq", "/app/input", "--tile", "192", "--tile_overlap", "16"]

# Usage
# Prepare two folders: input and output
#sudo docker run --gpus all -it -v $(pwd)/input:/app/input -v $(pwd)/output:/app/results/swinir_real_sr_x4_large tagname