#!/bin/bash

# 锁文件，防止任务重叠运行
LOCKFILE="/tmp/youtube_dl_job.lock"

if [ -e "${LOCKFILE}" ] && kill -0 `cat ${LOCKFILE}`; then
    echo "Previous job still running. Exiting."
    exit
fi

# 写入当前 PID 到锁文件
echo $$ > "${LOCKFILE}"

# 确保最后删除锁文件
trap "rm -f ${LOCKFILE}" EXIT

user_urls=(
    # ... (你的列表保持不变) ...
    "https://www.youtube.com/@yuan_zi_neng/videos"
    # ...
    "https://www.youtube.com/@ramosxin2340/videos"
)

echo "Starting daily download job at $(date)"

# 串行循环下载
for url in "${user_urls[@]}"; do
    echo "----------------------------------------------------------------"
    echo "Processing: $url"
    
    # 这里的参数优化解释：
    # --download-archive: 记录已下载视频 ID，避免重复
    # --match-filter: 排除掉直播中(is_live)的视频，避免卡住
    # --sleep-interval: 随机休眠 30-120秒，模拟人类观看间隔，防封锁
    # --format: 优先下载最佳 mp4 视频+最佳 m4a 音频
    
    youtube-dl \
        --ignore-errors \
        --no-progress \
        --format 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' \
        --merge-output-format mp4 \
        --download-archive '/mnt/data/youtube/archive.txt' \
        --cookies '/mnt/data/youtube/cookies.txt' \
        --match-filter "!is_live" \
        --write-description \
        --write-info-json \
        --write-annotations \
        --write-thumbnail \
        --write-sub \
        --all-subs \
        --embed-subs \
        --embed-thumbnail \
        --add-metadata \
        --sleep-interval 30 \
        --max-sleep-interval 120 \
        -o '/mnt/data/youtube/%(uploader)s/%(title)s.%(ext)s' \
        "$url"
        
    # 每个频道处理完后，稍微休息一下，避免请求过于密集
    echo "Finished $url, resting for 10 seconds..."
    sleep 10
done

# 清理非媒体文件 (Jellyfin 兼容性)
echo "Cleaning up webp/svg files..."
find /mnt/data/youtube/ -type f -name "*.webp" -delete
find /mnt/data/youtube/ -type f -name "*.svg" -delete

echo "Job finished at $(date)"