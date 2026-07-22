FROM hub.aiursoft.com/aiursoft/anduinos:resolute

RUN apt-get update && \
    apt install -y sudo bash libicu78 git unzip wget cron curl ca-certificates apt-transport-https software-properties-common

COPY ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources

RUN apt-get update && \
    apt upgrade -y && \
    rm -rf /var/lib/apt/lists/*