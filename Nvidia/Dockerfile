FROM hub.aiursoft.cn/nvidia/cuda:12.6.2-devel-ubuntu24.04

COPY source.list /etc/apt/sources.list
RUN apt-get update
RUN apt-get upgrade -y

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y tzdata && \
    echo "Etc/UTC" > /etc/timezone && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN apt-get install -y nvidia-cuda-toolkit \
    gcc g++ make cmake git sudo wget curl vim python3 python3-pip python-is-python3 \
    libgl1-mesa-dev libglib2.0-0 libsm6 libxext6 libxrender-dev libxext-dev libxrender-dev \
    libmpfr-dev libmpc-dev

RUN rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    apt-get autoclean && \
    apt-get autoremove -y