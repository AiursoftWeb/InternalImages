FROM hub.aiursoft.com/nvidia/cuda:12.6.2-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

COPY source.list /tmp/source.list

RUN if [ "$(uname -m)" = "x86_64" ]; then \
        mv /tmp/source.list /etc/apt/sources.list && \
        rm -v /etc/apt/sources.list.d/ubuntu*; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        tzdata \
        gcc g++ make cmake git sudo wget curl vim \
        python3 python3-pip python-is-python3 \
        libgl1-mesa-dev libglib2.0-0 libsm6 \
        libxext6 libxrender-dev libxext-dev \
        libmpfr-dev libmpc-dev pciutils && \
    echo "Etc/UTC" > /etc/timezone && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    apt-get clean && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*