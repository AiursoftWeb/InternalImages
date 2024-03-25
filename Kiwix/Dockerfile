# Kiwix Dockerfile
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

RUN apt update
RUN apt install -y kiwix-tools curl wget
RUN mkdir /data

EXPOSE 8080
VOLUME /data

ENTRYPOINT [ "sh", "-c", "/usr/bin/kiwix-serve --port 8080 /data/*.zim" ]