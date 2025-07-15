FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu-with-docker
WORKDIR /app
RUN apt-get update && \
    apt install -y cron python3 python-is-python3 python3-pip curl tmux && \
    rm -rf /var/lib/apt/lists/*

ADD "https://api.github.com/repos/regclient/regclient/commits?per_page=1" latest_commit

RUN curl -L https://github.com/regclient/regclient/releases/latest/download/regctl-linux-amd64 >regctl && \
    chmod 755 regctl && \
    mv regctl /usr/local/bin/

ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN pip install requests
      
# Copy entry script
COPY entry.sh /app/entry.sh
COPY check.py /app/check.py
COPY delete.py /app/delete.py
COPY is_latest.py /app/is_latest.py
RUN chmod +x /app/entry.sh

# Register a crontab job to run entry every day 3:00
#RUN crontab -l | { cat; echo "0 3 * * * /entry.sh"; } | crontab -

# Run /entry.sh with tmux
RUN echo "0 3 * * * root tmux new-session -d -s entry /app/entry.sh" > /etc/cron.d/entry-cron && echo "" >> /etc/cron.d/entry-cron
RUN chmod 0644 /etc/cron.d/entry-cron

# Run this job at the beginning with verbose output
#ENTRYPOINT ["cron", "-f", "-L 15"]

# Entry point should be: run the entry script once, then start cron
ENTRYPOINT ["sh", "-c", "tmux new-session -d -s entry /app/entry.sh && cron -f -L 15"]