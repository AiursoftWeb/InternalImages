FROM hub.aiursoft.cn/teddysun/xray

# No cache
ARG BuildDate=2025-06-15
ADD "https://api.github.com/repos/XTLS/Xray-core/commits?per_page=1" latest_commit

RUN mkdir -p /etc/xray
RUN mkdir -p /var/log/xray
RUN mkdir -p /etc/xray/cert

COPY ./config.json /etc/xray/config.json
COPY ./entry.sh /entry.sh

RUN apk add jq


EXPOSE 10000
VOLUME /var/log/xray

ENTRYPOINT [ "/bin/sh", "/entry.sh" ]