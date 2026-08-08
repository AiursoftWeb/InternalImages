FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal
WORKDIR /
COPY . .
RUN apt-get update && \
    apt-get install -y --no-install-recommends git jq cron curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN chmod +x /mirror.sh

VOLUME /opt/Source/Repos/

# Register a crontab job to run git-mirror every day
RUN crontab -l | { cat; echo "0 7 * * * /mirror.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]
