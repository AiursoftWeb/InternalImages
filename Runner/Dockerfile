FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu-with-docker
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY . .

# Replace ${arch} with any of the supported architectures, e.g. amd64, arm, arm64
# A full list of architectures can be found here https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/index.html
# curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner-helper-images.deb"
# curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner_${arch}.deb"

RUN curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner-helper-images.deb" && \
    curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner_amd64.deb" && \
    dpkg -i gitlab-runner-helper-images.deb && \
    dpkg -i gitlab-runner_amd64.deb && \
    rm -rf gitlab-runner-helper-images.deb gitlab-runner_amd64.deb

RUN curl -fsSL https://deb.nodesource.com/setup_23.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
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

# Enable docker in docker
RUN usermod -aG docker root && \
    usermod -aG systemd-journal gitlab-runner && \
    usermod -aG docker gitlab-runner && \
    usermod -aG sudo gitlab-runner

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
