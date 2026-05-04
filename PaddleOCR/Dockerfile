FROM hub.aiursoft.com/aiursoft/internalimages/nvidia:latest

# 系统依赖安装
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates python3 python3-pip python3-dev python3-venv \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# 创建并使用虚拟环境
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# 安装 PaddlePaddle (GPU版本) 和 PaddleOCR
RUN uv pip install \
    paddlepaddle-gpu==2.6.2 \
    paddleocr==2.8.0 \
    fastapi \
    uvicorn \
    python-multipart \
    opencv-python-headless \
    loguru \
    setuptools \
    requests \
    pymupdf

COPY . .

# 动态设置 LD_LIBRARY_PATH 指向系统 CUDA 13.2
ENV LD_LIBRARY_PATH="/usr/local/cuda-13.2/lib64:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
