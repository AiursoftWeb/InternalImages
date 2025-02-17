FROM hub.aiursoft.cn/ubuntu:24.10
COPY source.list /etc/apt/sources.list
RUN rm /etc/apt/sources.list.d/*
RUN apt update && \
    apt install -y sudo bash git unzip wget cron curl ca-certificates apt-transport-https software-properties-common && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*