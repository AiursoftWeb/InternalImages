FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu

# GitLab Runner.
RUN apt update
RUN apt install -y curl sudo
RUN curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | sudo bash
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
RUN apt update
RUN apt install -y gitlab-runner dotnet8 nodejs libgdiplus build-essential

COPY . /app
WORKDIR /app
ENTRYPOINT [ "/bin/bash", "-c", "/app/entry.sh" ]