FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

# Configure environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    NODE_MAJOR=24

# Install basic dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --yes && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Qwen Code CLI
RUN npm install -g @qwen-code/qwen-code@latest

# Install Python dependencies
RUN pip3 install --break-system-packages --ignore-installed \
    fastapi \
    uvicorn \
    loguru \
    pydantic

# Create directories
RUN mkdir -p /import
RUN mkdir -p /app

WORKDIR /app
COPY main.py .

# Set /import as a volume (suggested usage)
VOLUME /import

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["python3", "main.py"]
