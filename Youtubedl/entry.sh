#!/bin/bash

set -u

# 锁文件
LOCKFILE="/tmp/youtube_dl_job.lock"

# 检查是否存在锁
if [ -e "${LOCKFILE}" ] && kill -0 `cat ${LOCKFILE}` 2>/dev/null; then
    echo "Previous job still running. Exiting."
    exit
fi

echo $$ > "${LOCKFILE}"
trap "rm -f ${LOCKFILE}" EXIT

# 你的频道列表 (无需改动)
user_urls=(
    "https://www.youtube.com/@yuan_zi_neng/videos"
    "https://www.youtube.com/@Kassiapiano/videos"
    "https://www.youtube.com/@rousseau/videos"
    "https://www.youtube.com/@redknot-miaomiao/videos"
    "https://www.youtube.com/@MagicSecretsRevealed/videos"
    "https://www.youtube.com/@HsWrWwc/videos"
    "https://www.youtube.com/@thu4878/videos"
    "https://www.youtube.com/channel/UCf4YPrRO2clAH-zJcomJaGw/videos"
    "https://www.youtube.com/channel/UCSs4A6HYKmHA2MG_0z-F0xw/videos"
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
    "https://www.youtube.com/@lucaas/videos"
    "https://www.youtube.com/@ramosxin2340/videos"
    "https://www.youtube.com/@DarkCarrot-%E9%BB%91%E8%90%9D%E5%8D%9C/videos"
)

echo "Starting daily download job at $(date)"

# Cookies 是登录下载和避免机器人验证所必需的。缺失时停止任务，避免反复请求加重限流。
COOKIE_FILE="/mnt/data/youtube/cookies.txt"
if [ ! -s "${COOKIE_FILE}" ]; then
    echo "ERROR: Cookies file is missing or empty at ${COOKIE_FILE}."
    exit 1
fi
chmod 600 "${COOKIE_FILE}"

overall_status=0

for url in "${user_urls[@]}"; do
    echo "----------------------------------------------------------------"
    echo "Processing: $url"
    
    # 这里的 youtube-dl 实际上已经是 yt-dlp 了。
    # archive 中出现第一个旧视频后停止回溯，并限制每个频道最多检查最近 50 条，
    # 避免每天枚举频道完整历史并触发 YouTube 的 HTTP 429 限流。
    channel_status=0
    youtube-dl \
        --ignore-errors \
        --no-progress \
        --format 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' \
        --merge-output-format mp4 \
        --download-archive '/mnt/data/youtube/archive.txt' \
        --cookies "${COOKIE_FILE}" \
        --break-on-existing \
        --playlist-end 50 \
        --match-filter "!is_live" \
        --write-description \
        --write-info-json \
        --write-thumbnail \
        --write-sub \
        --all-subs \
        --embed-subs \
        --embed-thumbnail \
        --add-metadata \
        --sleep-requests 5 \
        --sleep-interval 30 \
        --max-sleep-interval 120 \
        -o '/mnt/data/youtube/%(uploader)s/%(title)s.%(ext)s' \
        "$url" || channel_status=$?

    if [ "${channel_status}" -eq 0 ]; then
        echo "Finished $url successfully, resting for 10 seconds..."
    elif [ "${channel_status}" -eq 101 ]; then
        echo "Finished $url at the existing archive boundary, resting for 10 seconds..."
    else
        overall_status=1
        echo "ERROR: $url failed with exit code ${channel_status}, resting for 10 seconds..."
    fi

    sleep 10
done

echo "Cleaning up webp/svg files..."
find /mnt/data/youtube/ -type f -name "*.webp" -delete
find /mnt/data/youtube/ -type f -name "*.svg" -delete

echo "Job finished at $(date)"
exit "${overall_status}"
