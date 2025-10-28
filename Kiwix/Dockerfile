# Kiwix Dockerfile
FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

RUN apt-get update
RUN apt-get install -y kiwix-tools curl wget
RUN mkdir /data

EXPOSE 8080
VOLUME /data

ENTRYPOINT [ "sh", "-c", "/usr/bin/kiwix-serve --port 8080 /data/*.zim" ]