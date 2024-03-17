FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

# GitLab Runner.
RUN apt update
RUN apt install -y curl sudo
RUN curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | sudo bash
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
RUN apt update
RUN apt install -y gitlab-runner dotnet8 nodejs libgdiplus build-essential

# Install Docker
RUN curl -fsSL https://get.docker.com -o get-docker.sh
ENV CHANNEL=stable
RUN sh get-docker.sh
RUN usermod -aG docker root
RUN usermod -aG docker gitlab-runner
RUN rm get-docker.sh

# Install .NET Tools
RUN sudo -u gitlab-runner dotnet tool install JetBrains.ReSharper.GlobalTools --global || echo "JB already installed."
RUN sudo -u gitlab-runner dotnet tool install dotnet-reportgenerator-globaltool --global || echo "ReportGenerator already installed."

COPY . /app
WORKDIR /app
RUN chmod +x /app/entry.sh
ENTRYPOINT [ "/bin/bash", "-c", "/app/entry.sh" ]