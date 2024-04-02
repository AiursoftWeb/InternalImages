FROM hub.aiursoft.cn/teddysun/xray

RUN mkdir -p /etc/xray
RUN mkdir -p /var/log/xray

EXPOSE 10000

VOLUME /var/log/xray

COPY ./config.json /etc/xray/config.json