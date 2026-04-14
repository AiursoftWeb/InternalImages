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
    pymupdf \
    nvidia-cudnn-cu12==8.9.2.26 \
    nvidia-cublas-cu12 \
    nvidia-cuda-runtime-cu12 \
    nvidia-cuda-nvcc-cu12 \
    nvidia-curand-cu12 \
    nvidia-cusolver-cu12 \
    nvidia-cusparse-cu12

COPY . .

# 自动建立软连接，修复库加载问题
RUN find /opt/venv/lib -name "*.so.*" -exec sh -c 'ln -s $(basename {}) $(dirname {})/$(basename {} | cut -d. -f1,2)' \; || true

# 动态设置 LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH="/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:/opt/venv/lib/python3.12/site-packages/nvidia/curand/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cusolver/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cusparse/lib:${LD_LIBRARY_PATH}"

# 设置 PaddlePaddle 显存控制环境变量避免碎片化
ENV FLAGS_allocator_strategy=auto_growth \
    FLAGS_eager_delete_tensor_gb=0.0 \
    FLAGS_fraction_of_gpu_memory_to_use=0.4 \
    FLAGS_allocator_strategy=naive_best_fit

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
