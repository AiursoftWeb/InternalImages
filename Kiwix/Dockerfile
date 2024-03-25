# Kiwix Dockerfile
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

RUN apt update
RUN apt install -y kiwix-tools curl

EXPOSE 8080
VOLUME /data
ENTRYPOINT ["kiwix-serve", "--port", "8080", "/data/*.zim"]
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD curl -f http://localhost:8080 || exit 1