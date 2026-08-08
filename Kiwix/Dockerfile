# Kiwix Dockerfile
FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal

RUN apt-get update && \
    apt-get install -y --no-install-recommends kiwix-tools curl wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN mkdir /data

EXPOSE 8080
VOLUME /data

ENTRYPOINT [ "sh", "-c", "/usr/bin/kiwix-serve --port 8080 /data/*.zim" ]
