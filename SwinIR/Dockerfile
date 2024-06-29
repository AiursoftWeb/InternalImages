FROM hub.aiursoft.cn/aiursoft/internalimages/nvidia:latest
WORKDIR /app
RUN sudo apt update && sudo apt install -y git
RUN git clone https://github.com/JingyunLiang/SwinIR.git

RUN pip install opencv-python torch torchvision
RUN pip install requests numpy timm

#003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth
RUN mkdir -p model_zoo/swinir && \
    wget -O model_zoo/swinir/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth

RUN mkdir -p /app/output

VOLUME /app/input
VOLUME /app/output

ENTRYPOINT ["python3", "main_test_swinir.py", "--task", "real_sr", "--scale", "4", "--model_path", "model_zoo/swinir/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth", "--folder_lq", "/app/input", "--folder_out", "/app/output", "--tile", "400"]
