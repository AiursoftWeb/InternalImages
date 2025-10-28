FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu-with-docker
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN curl -L https://github.com/regclient/regclient/releases/latest/download/regctl-linux-amd64 >regctl && \
    chmod 755 regctl && \
    mv regctl /usr/local/bin/

RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
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

RUN dotnet tool install JetBrains.ReSharper.GlobalTools --global --add-source https://nuget.aiursoft.com/v3/index.json -v d || echo 'JB already installed.' && \
    dotnet tool install dotnet-reportgenerator-globaltool --global --add-source https://nuget.aiursoft.com/v3/index.json -v d || echo 'ReportGenerator already installed.'

RUN npm config set registry https://npm.aiursoft.com && \
    npm install -g typescript ts-node npm yarn --loglevel verbose

RUN echo "fs.inotify.max_user_instances=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_user_watches=524288" >> /etc/sysctl.conf && \
    echo "fs.inotify.max_queued_events=524288" >> /etc/sysctl.conf && \
    sysctl -p
