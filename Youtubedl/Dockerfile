FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

WORKDIR /root

# 安装必要的依赖，加入 ffmpeg 和 python
RUN apt-get update && \
    apt install python3 python3-pip python-is-python3 ffmpeg atomicparsley git sudo cron pipx -y && \
    rm -rf /var/lib/apt/lists/*

# Allow pip to break system packages
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Avoid Docker cache for yt-dlp update
ADD "https://api.github.com/repos/yt-dlp/yt-dlp/commits?per_page=1" latest_commit

# 安装 yt-dlp (它是现在的版本答案)
RUN pipx install yt-dlp && \
    mv /root/.local/bin/yt-dlp /usr/bin/yt-dlp && \
    chmod +x /usr/bin/yt-dlp && \
    # 做个软链接，这样你脚本里的 youtube-dl 命令依然有效
    ln -s /usr/bin/yt-dlp /usr/bin/youtube-dl && \
    /usr/bin/youtube-dl --version

COPY ./entry.sh /entry.sh
RUN chmod +x /entry.sh
RUN mkdir -p /mnt/data

VOLUME /mnt/data

# 注册 Cron 任务
RUN crontab -l | { cat; echo "0 6 * * * /entry.sh >> /var/log/cron_job.log 2>&1"; } | crontab -

# 启动 Cron
# 建议创建日志文件以便 tail 查看
RUN touch /var/log/cron_job.log
ENTRYPOINT ["cron", "-f", "-L 15"]