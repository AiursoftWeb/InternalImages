FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

# 系统依赖安装：Python, FFmpeg (PaddleOCR需要), 以及必要的图形库
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates python3 python3-pip python3-dev python3-venv \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# 安装 uv 以加速后续 Python 包安装
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# 创建并使用虚拟环境
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# 安装 PaddlePaddle (CPU版本) 和 PaddleOCR
RUN uv pip install \
    paddlepaddle \
    paddleocr \
    fastapi \
    uvicorn \
    python-multipart \
    opencv-python-headless \
    loguru

# 预下载 OCR 模型
RUN python3 -c "from paddleocr import PaddleOCR; PaddleOCR(use_textline_orientation=True, lang='ch')"

COPY . .

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
