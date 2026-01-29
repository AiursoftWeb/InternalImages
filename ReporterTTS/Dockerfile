# ==========================================
# Build Stage (构建阶段)
# ==========================================
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

# 1. 安装构建所需的系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    git \
    pkg-config \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装 Rust (使用 rustup)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# 3. 设置工作目录
WORKDIR /app

# 4. 复制项目文件
# 为了利用 Docker 缓存，建议先复制 Cargo 配置文件下载依赖（可选优化），
# 但为了简单起见，这里直接复制所有文件
COPY . .

# 5. 编译 Server (CUDA 版本)
# 注意：如果需要 Flash Attention (更极端的性能)，可以添加 --features flash-attn
# 但这会显著增加编译时间和内存消耗(需16GB+ RAM)，因此默认仅开启 cuda
RUN cargo build --release --bin server --features cuda

# ==========================================
# Runtime Stage (运行阶段)
# ==========================================
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# 1. 安装运行时依赖 (主要是 SSL 和 CA 证书，用于下载模型)
RUN apt-get update && apt-get install -y \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 从构建阶段复制编译好的二进制文件
COPY --from=builder /app/target/release/server /usr/local/bin/server

# 3. 复制 voice-template 目录 (运行时需要)
COPY --from=builder /app/voices-template /app/voices-template

# 4. 创建模型缓存目录 (用于挂载 Volume)
RUN mkdir -p /root/.cache/huggingface /root/.cache/candle

# 5. 暴露端口
EXPOSE 3000

# 6. 设置入口点
# 默认使用 voices-template 目录启动
ENTRYPOINT ["server"]
CMD ["--voice-dir", "voices-template"]