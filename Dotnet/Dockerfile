FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu:latest

# Install dotnet, also install curl and wget because they are often used in dotnet containers.
RUN apt update && \
    apt install -y dotnet9 curl wget \
    && apt clean
