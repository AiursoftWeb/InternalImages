FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal

RUN apt-get update && \
    apt-get install -y docker.io && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
