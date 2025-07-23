#!/bin/bash
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
)

# Loop through user URLs and start a new tmux session for each channel
for url in "${user_urls[@]}"; do
    # Extract the user ID from the URL
    user_id=$(echo "$url" | grep -oP '(?<=youtube.com/@)[^/]+')
    echo "Starting download $url"
    date
    # Start a new tmux session for the channel
    tmux new -d -s "$user_id" "\
youtube-dl \
    -f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' \
    --download-archive '/mnt/data/youtube/$user_id.txt' \
    --cookies '/mnt/data/youtube/cookies.txt' \
    --write-description \
    --write-info-json \
    --write-annotations \
    --write-thumbnail \
    --write-sub \
    --all-subs \
    --ignore-errors \
    --merge-output-format mp4 \
    --add-metadata \
    --embed-subs \
    --embed-thumbnail \
    --sleep-interval 500 \
    --max-sleep-interval 1000 \
    -o '/mnt/data/youtube/%(uploader)s/%(title)s.%(ext)s' $url && echo 'Download complete' || echo 'Download failed' && sleep 1800"
    echo "Running command: youtube-dl -o '/mnt/data/youtube/%(uploader)s/%(title)s.%(ext)s' $url in tmux session $user_id"
    tmux list-sessions
    echo "Sleeping for 800 seconds"
    sleep 800
done

# Delete all .webp files because it may cause jellyfin to crash
find /mnt/data/youtube/ -type f -name "*.webp" -delete
find /mnt/data/youtube/ -type f -name "*.svg" -delete