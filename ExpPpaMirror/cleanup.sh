#!/bin/sh
# cleanup.sh - v4 (修复 subshell 计数问题)
# 删除作为目录缓存的 APT 元数据，并详细记录

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "开始执行 APT 元数据清理任务 (目录模式)..."

CACHE_PATH="/data/ubuntu/dists"

if [ ! -d "$CACHE_PATH" ]; then
    log "缓存目录 $CACHE_PATH 不存在，跳过清理。"
    exit 0
fi

# 查找所有需要删除的目录，并将结果存入变量
dirs_to_delete=$(find "$CACHE_PATH" -mindepth 2 -type d \( -name "InRelease" -o -name "Release" -o -name "Release.gpg" -o -name "Packages*" -o -name "Sources*" -o -name "Contents-*" \))

# 检查是否有需要删除的目录
if [ -z "$dirs_to_delete" ]; then
    log "没有找到需要清理的元数据目录。"
else
    # 核心修正：在循环外部计算文件数量
    # `grep -c .` 会计算非空行的数量，比 `wc -l` 更健壮
    deleted_count=$(echo -n "$dirs_to_delete" | grep -c .)

    log "准备清理 ${deleted_count} 个元数据目录及其全部内容:"
    
    # 循环只负责打印日志和删除，不再需要计数
    echo "$dirs_to_delete" | while IFS= read -r dir; do
        if [ -n "$dir" ]; then
            log "  => 正在删除目录: $dir"
            # 使用 rm -rf 来递归删除整个目录
            rm -rf "$dir"
        fi
    done

    log "汇总：总共清理了 ${deleted_count} 个元数据目录。"
fi

log "清理任务完成。"