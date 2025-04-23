FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

WORKDIR /root

RUN apt update && \
    apt install python3 python3-pip python-is-python3 ffmpeg atomicparsley git sudo tmux cron pipx -y && \
    rm -rf /var/lib/apt/lists/*

# Allow pip to break system packages
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Avoid Docker cache
ADD https://api.github.com/repos/ytdl-org/youtube-dl/branches/master skipcache

RUN pipx install 'git+https://github.com/ytdl-org/youtube-dl.git@master#egg=youtube_dl' && \
    mv /root/.local/bin/youtube-dl /usr/bin/youtube-dl && \
    chmod +x /usr/bin/youtube-dl && \
    /usr/bin/youtube-dl --version

COPY ./entry.sh /entry.sh
RUN chmod +x /entry.sh
RUN mkdir -p /mnt/data

VOLUME /mnt/data

# Register a crontab job to run youtube-dl every day at 6:00
RUN crontab -l | { cat; echo "0 6 * * * /entry.sh"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]