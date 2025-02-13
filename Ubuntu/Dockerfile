FROM hub.aiursoft.cn/ubuntu:24.10
COPY source.list /etc/apt/sources.list
RUN rm /etc/apt/sources.list.d/*
RUN apt update && \
    apt install -y git unzip wget cron curl --no-install-recommends && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*