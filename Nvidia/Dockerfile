FROM hub.aiursoft.cn/nvidia/cuda:11.8.0-devel-ubuntu22.04

COPY source.list /etc/apt/sources.list
RUN apt update
RUN apt upgrade -y
RUN apt install -y tzdata && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata
RUN apt install install -y nvidia-cuda-toolkit \
    gcc g++ make cmake git sudo wget curl vim python3 python3-pip python-is-python3 \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libxext-dev libxrender-dev