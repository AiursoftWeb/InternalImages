#!/bin/sh

# 启动 cron 服务
# 在 Ubuntu/Debian 中，标准方式是使用 service 命令
service cron start
echo "Cron service has been started."

# 在前台启动 static 文件服务器
# exec 会用 static 进程替换当前的 shell 进程，这是容器最佳实践
echo "Starting static file server..."
exec /app/static --port 5000 --path /data/ --mirror http://ppa.launchpad.net/ --cache-mirror