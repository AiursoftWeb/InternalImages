# 使用您确认的 Ubuntu 基础镜像
FROM hub.aiursoft.com/aiursoft/static

# 使用 apt-get 安装 cron 服务
# RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y cron
# 上面的命令可能会因为没有 sudo 而失败，根据基础镜像的配置，直接安装可能更有效
RUN apt-get update && \
    apt-get install -y cron && \
    # 清理 apt 缓存以减小镜像体积
    rm -rf /var/lib/apt/lists/*

# 创建数据目录
RUN mkdir -p /data

# 复制 cron 任务文件到 Ubuntu 的 cron 目录
COPY static-mirror-cleanup /etc/cron.d/static-mirror-cleanup

# 复制脚本文件
COPY cleanup.sh /usr/local/bin/cleanup.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# 赋予文件正确的权限
# cron 任务文件不应有执行权限
# 脚本文件需要有执行权限
RUN chmod 0644 /etc/cron.d/static-mirror-cleanup && \
    chmod +x /usr/local/bin/cleanup.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

# 设置容器的入口点
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]