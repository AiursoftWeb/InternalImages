FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    CHANNEL=stable sh get-docker.sh && \
    usermod -aG docker root && \
    chmod 660 /var/run/docker.sock && \
    rm get-docker.sh
