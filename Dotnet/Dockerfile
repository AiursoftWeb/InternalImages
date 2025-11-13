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
    libatomic1 \
    wget && \
    rm -rf /var/lib/apt/lists/* && \
    touch /.dockerenv

RUN wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh && \
    chmod +x dotnet-install.sh && \
    ./dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet && \
    ln -s /usr/share/dotnet/dotnet /usr/bin/dotnet && \
    rm dotnet-install.sh

RUN dotnet --info && echo $ASPNETCORE_ENVIRONMENT && \
    echo "Environment setup complete."