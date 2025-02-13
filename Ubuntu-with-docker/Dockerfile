FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    CHANNEL=stable sh get-docker.sh && \
    usermod -aG docker root && \
    rm get-docker.sh
