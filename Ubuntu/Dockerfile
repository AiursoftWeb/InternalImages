FROM hub.aiursoft.com/ubuntu:25.10

RUN apt-get update && \
    apt install -y sudo bash libicu76 git unzip wget cron curl ca-certificates apt-transport-https software-properties-common

COPY source.list /tmp/source.list
RUN if [ "$(uname -m)" = "x86_64" ]; then \
        mv /tmp/source.list /etc/apt/sources.list && \
        rm -rf /etc/apt/sources.list.d/*; \
    fi

RUN apt-get update && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*