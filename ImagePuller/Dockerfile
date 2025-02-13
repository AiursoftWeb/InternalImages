FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /
RUN apt update
RUN apt install -y git unzip wget cron curl

# Install Docker
RUN curl -fsSL https://get.docker.com -o get-docker.sh
ENV CHANNEL=stable
RUN sh get-docker.sh
RUN usermod -aG docker root
RUN chmod 660 /var/run/docker.sock
RUN rm get-docker.sh

# Copy entry script
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh

# Register a crontab job to run entry every day 3:00
RUN crontab -l | { cat; echo "0 3 * * * /entry.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]