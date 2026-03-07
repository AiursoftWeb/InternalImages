FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

WORKDIR /root

# 1. 安装依赖
RUN apt-get update && \
    apt install python3 python-is-python3 ffmpeg atomicparsley git sudo cron curl -y && \
    rm -rf /var/lib/apt/lists/*

# 2. 设置环境变量 (至关重要！)
# 解决 Cron 中文文件名乱码或报错的问题
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Avoid Docker cache
ADD "https://api.github.com/repos/yt-dlp/yt-dlp/commits?per_page=1" latest_commit

# 3. 安装 yt-dlp (直接从 GitHub Releases 下载二进制，避免跨平台构建时 PyPI SSL 问题)
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        YT_DLP_BIN="yt-dlp_linux_aarch64"; \
    else \
        YT_DLP_BIN="yt-dlp_linux"; \
    fi && \
    curl -L "https://github.com/yt-dlp/yt-dlp/releases/latest/download/${YT_DLP_BIN}" -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp && \
    ln -sf /usr/local/bin/yt-dlp /usr/bin/yt-dlp && \
    ln -sf /usr/local/bin/yt-dlp /usr/bin/youtube-dl && \
    yt-dlp --version

COPY ./entry.sh /entry.sh
RUN chmod +x /entry.sh
RUN mkdir -p /mnt/data

VOLUME /mnt/data

# 4. 注册 Cron 任务
# 增加了一个环境导入操作，确保 Cron 能读取到 Docker 的环境变量
RUN touch /var/log/cron_job.log
RUN echo "PYTHONIOENCODING=utf-8" >> /etc/environment
RUN crontab -l | { cat; echo "0 6 * * * . /etc/environment; /entry.sh >> /var/log/cron_job.log 2>&1"; } | crontab -

# 启动
ENTRYPOINT ["cron", "-f", "-L 15"]