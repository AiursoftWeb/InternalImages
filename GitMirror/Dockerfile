FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /
COPY . .
RUN apt update
RUN apt install -y git jq cron

VOLUME /opt/Source/Repos/

# Register a crontab job to run apt-mirror every day
RUN crontab -l | { cat; echo "0 7 * * * /mirror.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]