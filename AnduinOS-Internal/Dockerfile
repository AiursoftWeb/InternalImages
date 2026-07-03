FROM hub.aiursoft.com/aiursoft/anduinos:resolute

RUN apt-get update && \
    apt install -y sudo bash libicu78 git unzip wget cron curl ca-certificates apt-transport-https software-properties-common

COPY ubuntu.sources /tmp/ubuntu.sources
COPY ubuntu.sources.arm /tmp/ubuntu.sources.arm
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        mv /tmp/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources; \
    elif [ "$ARCH" = "aarch64" ]; then \
        mv /tmp/ubuntu.sources.arm /etc/apt/sources.list.d/ubuntu.sources; \
    fi

RUN apt-get update && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*