FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu:latest

# Configure environment variables
ENV ASPNETCORE_ENVIRONMENT="Production" \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_PRINT_TELEMETRY_MESSAGE="false" \
    ASPNETCORE_FORWARDEDHEADERS_ENABLED="true" \
    DOTNET_RUNNING_IN_CONTAINER="true" \
    DOTNET_GENERATE_ASPNET_CERTIFICATE=false \
    DOTNET_NOLOGO=true \
    ASPNETCORE_HTTP_PORTS=5000 \
    DOTNET_USE_POLLING_FILE_WATCHER=true \
    NUGET_XMLDOC_MODE=skip

# Install dotnet, also install curl and wget because they are often used in dotnet containers.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    libicu76 \
    libatomic1 \
    dotnet10 \
    wget && \
    rm -rf /var/lib/apt/lists/* && \
    touch /.dockerenv

RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --yes && \
    NODE_MAJOR=24 && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN dotnet --info && echo $ASPNETCORE_ENVIRONMENT && \
    echo "Environment setup complete."