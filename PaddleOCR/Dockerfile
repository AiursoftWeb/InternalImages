FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu:latest

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

# 安装 PaddlePaddle (CPU版本) 和 PaddleOCR
RUN uv pip install \
    paddlepaddle==3.3.1 \
    paddleocr==3.5.0 \
    fastapi \
    uvicorn \
    python-multipart \
    opencv-python-headless \
    loguru \
    setuptools \
    requests \
    pymupdf

COPY . .

# 预热：触发模型下载并缓存到镜像中，避免首次请求时才下载
RUN python3 -c "\
import numpy as np, cv2; \
from paddleocr import PaddleOCR; \
ocr = PaddleOCR(use_textline_orientation=True, lang='ch', device='cpu', enable_mkldnn=False); \
img = np.ones((64, 256, 3), dtype=np.uint8) * 255; \
cv2.putText(img, 'warmup', (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2); \
ocr.ocr(img); \
print('Model warmup done.') \
"

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
