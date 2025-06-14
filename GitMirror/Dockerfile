FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /
COPY . .
RUN apt-get update && apt install -y git jq cron curl
RUN chmod +x /mirror.sh

VOLUME /opt/Source/Repos/

# Register a crontab job to run git-mirror every day
RUN crontab -l | { cat; echo "0 7 * * * /mirror.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]