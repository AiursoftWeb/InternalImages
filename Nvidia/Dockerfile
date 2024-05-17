FROM hub.aiursoft.cn/nvidia/cuda:11.6.2-base-ubuntu20.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-cuda-toolkit gcc g++ make cmake