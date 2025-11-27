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
    "https://www.youtube.com/@yuan_zi_neng/videos"
    "https://www.youtube.com/@Kassiapiano/videos"
    "https://www.youtube.com/@rousseau/videos"
    "https://www.youtube.com/@redknot-miaomiao/videos"
    "https://www.youtube.com/@MagicSecretsRevealed/videos"
    "https://www.youtube.com/@HsWrWwc/videos"
    "https://www.youtube.com/@thu4878/videos"
    "https://www.youtube.com/@user-lk3gk5sd7n/videos"
    "https://www.youtube.com/@TchLiyongle/videos"
    "https://www.youtube.com/@SONAR606/videos"
    "https://www.youtube.com/@anduinxue4729/videos"
    "https://www.youtube.com/@STBoss/videos"
    "https://www.youtube.com/@gleekid/videos"
    "https://www.youtube.com/@paperclip6992/videos"
    "https://www.youtube.com/@xdiaocha/videos"
    "https://www.youtube.com/@GPINTALK/videos"
    "https://www.youtube.com/@xiaohan-ufo/videos"
    "https://www.youtube.com/@JaredOwen/videos"
    "https://www.youtube.com/@%E7%A1%AC%E4%BB%B6%E8%8C%B6%E8%B0%88/videos"
    "https://www.youtube.com/@%E8%B5%B5%E9%9D%9E%E5%90%8C/videos"
    "https://www.youtube.com/@geekerwan1024/videos"
    "https://www.youtube.com/@wbclg/videos"
    "https://www.youtube.com/@user-darkcarrot/videos"
    "https://www.youtube.com/@xiao_lin_shuo/videos"
    #"https://www.youtube.com/@AkilaZhang/videos"
    "https://www.youtube.com/@dacongmovie/videos"
    "https://www.youtube.com/@chesspage1real/videos"
    "https://www.youtube.com/@BossPrating/videos"
    "https://www.youtube.com/@ssrphysics/videos"
    "https://www.youtube.com/@One-In-a-Billion/videos"
    "https://www.youtube.com/@3blue1brown/videos"
    "https://www.youtube.com/@FView-CN/videos"
    "https://www.youtube.com/@manshi_math/videos"
    "https://www.youtube.com/@cyzstudio/videos"
    "https://www.youtube.com/@mediastorm6801/videos"
    "https://www.youtube.com/@YAGP/videos"
    "https://www.youtube.com/@yugu233/videos"
    "https://www.youtube.com/@1kdoc/videos"
    "https://www.youtube.com/@hippopotamus85/videos"
    "https://www.youtube.com/@hippo20251/videos"
    "https://www.youtube.com/@xiao_lin_shuo/videos"
    "https://www.youtube.com/@lucaas/videos"
    "https://www.youtube.com/@ramosxin2340/videos"
    "https://www.youtube.com/@DarkCarrot-%E9%BB%91%E8%90%9D%E5%8D%9C/videos"
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