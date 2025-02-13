FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu-with-docker
WORKDIR /
RUN apt update
RUN apt install -y git unzip wget cron curl

# Copy entry script
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh

# Register a crontab job to run entry every day 3:00
RUN crontab -l | { cat; echo "0 3 * * * /entry.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]