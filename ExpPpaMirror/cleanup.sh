#!/bin/sh
# cleanup.sh - v5 (增加网络检查，修复 subshell 计数问题)
# 删除作为目录缓存的 APT 元数据，并详细记录

log() {
    # 打印带时间戳的日志信息
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "开始执行 APT 元数据清理任务 (目录模式)..."

# --- 新增网络检查 ---
HOSTNAME_TO_CHECK="archive.ubuntu.com"
log "正在检查网络连接: $HOSTNAME_TO_CHECK..."

# 使用 ping 命令检查网络连通性
# -c 1: 只发送1个ICMP数据包
# -W 5: 设置超时时间为5秒
if ! ping -c 1 -W 5 "$HOSTNAME_TO_CHECK" > /dev/null 2>&1; then
    log "错误: 无法连接到 $HOSTNAME_TO_CHECK。请检查网络连接。"
    log "清理任务已取消。"
    exit 1
else
    log "网络连接正常，继续执行清理。"
fi
# --- 网络检查结束 ---

CACHE_PATH="/data/ubuntu/dists"

if [ ! -d "$CACHE_PATH" ]; then
    log "缓存目录 $CACHE_PATH 不存在，跳过清理。"
    exit 0
fi

# 查找所有需要删除的目录，并将结果存入变量
# -mindepth 2: 避免删除 dists 下的一级目录 (如 bionic, focal)
# -type d: 只查找目录
# \( ... \): 匹配多个名称模式
dirs_to_delete=$(find "$CACHE_PATH" -mindepth 2 -type d \( -name "InRelease" -o -name "Release" -o -name "Release.gpg" -o -name "Packages*" -o -name "Sources*" -o -name "Contents-*" \))

# 检查是否有需要删除的目录
if [ -z "$dirs_to_delete" ]; then
    log "没有找到需要清理的元数据目录。"
else
    # 在循环外部计算目录数量，避免在 subshell 中计数导致的问题
    # `grep -c .` 会计算非空行的数量，比 `wc -l` 更健壮
    deleted_count=$(echo -n "$dirs_to_delete" | grep -c .)

    log "准备清理 ${deleted_count} 个元数据目录及其全部内容:"
    
    # 循环遍历并删除每个找到的目录
    echo "$dirs_to_delete" | while IFS= read -r dir; do
        if [ -n "$dir" ]; then
            log "  => 正在删除目录: $dir"
            # 使用 rm -rf 来递归删除整个目录及其内容
            rm -rf "$dir"
        fi
    done

    log "汇总：总共清理了 ${deleted_count} 个元数据目录。"
fi

log "清理任务完成。"
