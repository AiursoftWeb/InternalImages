FROM hub.aiursoft.com/ubuntu:25.10

COPY source.list /tmp/new_sources.list
COPY source.list.arm /tmp/new_sources.list.arm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        apt-transport-https \
        bash \
        unzip \
        wget \
        curl && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        mv /tmp/new_sources.list /etc/apt/sources.list; \
    elif [ "$ARCH" = "aarch64" ]; then \
        mv /tmp/new_sources.list.arm /etc/apt/sources.list; \
    fi && \
    rm -rf /etc/apt/sources.list.d/* && \
    apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*