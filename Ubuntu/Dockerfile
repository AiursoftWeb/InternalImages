FROM hub.aiursoft.com/ubuntu:25.10

RUN apt-get update && \
    apt install -y sudo bash libicu76 git unzip wget cron curl ca-certificates apt-transport-https software-properties-common

COPY source.list /tmp/source.list
COPY source.list.arm /tmp/source.list.arm
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        mv /tmp/source.list /etc/apt/sources.list; \
    elif [ "$ARCH" = "aarch64" ]; then \
        mv /tmp/source.list.arm /etc/apt/sources.list; \
    fi && \
    rm -rf /etc/apt/sources.list.d/*

RUN apt-get update && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*