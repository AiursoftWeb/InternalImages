FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu-with-docker
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY . .

# Install regctl
RUN curl -L https://github.com/regclient/regclient/releases/latest/download/regctl-linux-amd64 >regctl && \
    chmod 755 regctl && \
    mv regctl /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Apt tools
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
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
      python3-pip \
      shellcheck \
      dotnet10 && \
    rm -rf /var/lib/apt/lists/*

# Python packages
RUN pip install PyYAML

# .NET Global Tools
RUN dotnet tool install JetBrains.ReSharper.GlobalTools --global --add-source https://nuget.aiursoft.com/v3/index.json -v d || echo 'JB already installed.' && \
    dotnet tool install dotnet-reportgenerator-globaltool --global --add-source https://nuget.aiursoft.com/v3/index.json -v d || echo 'ReportGenerator already installed.'

# Node.js Global Tools
RUN npm config set registry https://npm.aiursoft.com && \
    npm install -g typescript ts-node npm yarn --loglevel verbose

# Increase inotify limits
RUN echo "fs.inotify.max_user_instances=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_user_watches=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_queued_events=524288" >> /etc/sysctl.conf && \
    sysctl -p

# Install GitLab Runner
RUN curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner-helper-images.deb" && \
    curl -LJO "https://s3.dualstack.us-east-1.amazonaws.com/gitlab-runner-downloads/latest/deb/gitlab-runner_amd64.deb" && \
    dpkg -i gitlab-runner-helper-images.deb && \
    dpkg -i gitlab-runner_amd64.deb && \
    rm -rf gitlab-runner-helper-images.deb gitlab-runner_amd64.deb

# Enable docker in docker
RUN usermod -aG docker root && \
    usermod -aG systemd-journal gitlab-runner && \
    usermod -aG docker gitlab-runner && \
    usermod -aG sudo gitlab-runner

# Create a directory for data
RUN mkdir /data && chmod 777 /data && \
    chmod +x /app/entry.sh

ENTRYPOINT ["/bin/bash", "-c", "/app/entry.sh"]
