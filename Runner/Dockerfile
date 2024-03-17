FROM hub.aiursoft.cn/ubuntu

# GitLab Runner.
RUN apt update
RUN apt install -y gitlab-runner dotnet8 nodejs libgdiplus build-essential

COPY . /app
WORKDIR /app
ENTRYPOINT [ "/app/entry.sh" ]