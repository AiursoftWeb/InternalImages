FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

# GitLab Runner.
RUN apt update
RUN apt install -y curl sudo apt-transport-https ca-certificates software-properties-common
RUN curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | sudo bash
RUN curl -fsSL https://deb.nodesource.com/setup_21.x | sudo -E bash -
RUN apt update
RUN apt install -y gitlab-runner dotnet8 nodejs libgdiplus build-essential bc ffmpeg zip unzip tar gzip iputils-ping net-tools git jq

# Install Docker
RUN curl -fsSL https://get.docker.com -o get-docker.sh
ENV CHANNEL=stable
RUN sh get-docker.sh
RUN usermod -aG docker root
RUN usermod -aG docker gitlab-runner
RUN rm get-docker.sh

# Install .NET Tools
RUN sudo -u gitlab-runner dotnet tool install JetBrains.ReSharper.GlobalTools --global --add-source https://nuget.aiursoft.cn/v3/index.json -v d || echo "JB already installed."
RUN sudo -u gitlab-runner dotnet tool install dotnet-reportgenerator-globaltool --global --add-source https://nuget.aiursoft.cn/v3/index.json -v d || echo "ReportGenerator already installed."

# Install Node Tools
RUN sudo npm install typescript ts-node npm -g

# Hack inode
RUN echo fs.inotify.max_user_instances=524288 | tee -a /etc/sysctl.conf
RUN echo fs.inotify.max_user_watches=524288 | tee -a /etc/sysctl.conf
RUN echo fs.inotify.max_queued_events=524288 | tee -a /etc/sysctl.conf
RUN sysctl -p

COPY . /app
WORKDIR /app
RUN chmod +x /app/entry.sh

ENTRYPOINT [ "/bin/bash", "-c", "/app/entry.sh" ]