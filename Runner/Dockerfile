FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY . .

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      sudo \
      apt-transport-https \
      ca-certificates \
      software-properties-common && \
    curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | bash && \
    curl -fsSL https://deb.nodesource.com/setup_23.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      gitlab-runner \
      dotnet9 \
      nodejs \
      libgdiplus \
      build-essential \
      bc \
      ffmpeg \
      zip \
      unzip \
      tar \
      gzip \
      iputils-ping \
      net-tools \
      git \
      jq \
      shellcheck && \
    rm -rf /var/lib/apt/lists/*

# 安装 Docker 并调整相关用户组
RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    CHANNEL=stable sh get-docker.sh && \
    usermod -aG docker root && \
    usermod -aG systemd-journal gitlab-runner && \
    usermod -aG docker gitlab-runner && \
    usermod -aG sudo gitlab-runner && \
    rm get-docker.sh

RUN su - gitlab-runner -c "dotnet tool install JetBrains.ReSharper.GlobalTools --global --add-source https://nuget.aiursoft.cn/v3/index.json -v d || echo 'JB already installed.'" && \
    su - gitlab-runner -c "dotnet tool install dotnet-reportgenerator-globaltool --global --add-source https://nuget.aiursoft.cn/v3/index.json -v d || echo 'ReportGenerator already installed.'"

RUN npm config set registry https://npm.aiursoft.cn && \
    npm install -g typescript ts-node npm yarn --loglevel verbose

RUN echo "fs.inotify.max_user_instances=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_user_watches=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_queued_events=524288" >> /etc/sysctl.conf && \
    sysctl -p

RUN mkdir /data && chmod 777 /data && \
    chmod +x /app/entry.sh

ENTRYPOINT ["/bin/bash", "-c", "/app/entry.sh"]
