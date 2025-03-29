FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu-with-docker
WORKDIR /
RUN apt update && \
    apt install -y cron && \
    rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/regclient/regclient/releases/latest/download/regctl-linux-amd64 >regctl && \
    chmod 755 regctl && \
    mv regctl /usr/local/bin/

# Copy entry script
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh

# Register a crontab job to run entry every day 3:00
RUN crontab -l | { cat; echo "0 3 * * * /entry.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]