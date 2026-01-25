FROM hub.aiursoft.com/ubuntu:25.10

RUN apt-get update && \
    apt install -y sudo bash libicu76 git unzip wget cron curl ca-certificates apt-transport-https

COPY source.list /etc/apt/sources.list
RUN rm /etc/apt/sources.list.d/*

RUN apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*