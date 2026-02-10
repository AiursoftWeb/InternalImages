FROM hub.aiursoft.com/ubuntu:25.10

COPY source.list /tmp/new_sources.list

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        apt-transport-https \
        bash \
        unzip \
        wget \
        curl && \
    mv /tmp/new_sources.list /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/* && \
    apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*