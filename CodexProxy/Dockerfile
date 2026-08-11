# ==========================================
# 第一阶段：构建阶段 (Builder)
# ==========================================
FROM hub.aiursoft.com/rust:latest AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        git pkg-config libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 【修复处】：将 latest_commit 下载到 /tmp 目录，保持 /build 目录为空
ADD "https://api.github.com/repos/Securiteru/codex-openai-proxy/commits?per_page=1" /tmp/latest_commit

# 现在 /build 是空的了，克隆就不会报错了
RUN git clone --depth 1 https://github.com/Securiteru/codex-openai-proxy.git .

RUN cargo build --release

# ==========================================
# 第二阶段：运行阶段 (Runtime)
# ==========================================
FROM hub.aiursoft.com/aiursoft/internalimages/anduinos-internal:latest

# 1. 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tzdata libssl3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 2. 创建普通用户
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /usr/sbin/nologin -m appuser

WORKDIR /app

# 3. 复制编译产物，并赋予权限
COPY --from=builder --chown=appuser:appgroup /build/target/release/codex-openai-proxy /app/codex-openai-proxy

# 4. 创建程序需要的配置目录
RUN mkdir -p /home/appuser/.codex && \
    chown -R appuser:appgroup /home/appuser/.codex

# 5. 切换到非 root 用户
USER appuser:appgroup

ENV TZ="UTC" \
    RUST_LOG="info" \
    HOME="/home/appuser"

VOLUME /home/appuser/.codex
EXPOSE 8080

CMD ["./codex-openai-proxy", "--port", "8080"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:8080/v1/models || exit 1