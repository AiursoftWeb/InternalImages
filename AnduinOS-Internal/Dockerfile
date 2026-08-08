FROM hub.aiursoft.com/aiursoft/anduinos:resolute

COPY ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        cron \
        curl \
        git \
        libicu78 \
        software-properties-common \
        sudo \
        unzip \
        wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
