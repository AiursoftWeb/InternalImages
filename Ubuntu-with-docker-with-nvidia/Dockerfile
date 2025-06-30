FROM hub.aiursoft.cn/aiursoft/internalimages/nvidia

# Nvidia + Docker.
RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    CHANNEL=stable sh get-docker.sh && \
    usermod -aG docker root && \
    rm get-docker.sh

# Nvidia + Docker + Container Toolkit.
RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    sudo apt-get update \
    sudo apt-get install -y nvidia-container-toolkit nvidia-docker2
