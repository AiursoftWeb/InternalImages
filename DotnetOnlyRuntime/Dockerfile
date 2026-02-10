FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu-mini:latest

# Configure environment variables
ENV ASPNETCORE_ENVIRONMENT="Production" \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_PRINT_TELEMETRY_MESSAGE="false" \
    ASPNETCORE_FORWARDEDHEADERS_ENABLED="true" \
    DOTNET_RUNNING_IN_CONTAINER="true" \
    DOTNET_GENERATE_ASPNET_CERTIFICATE=false \
    DOTNET_NOLOGO=true \
    ASPNETCORE_HTTP_PORTS=5000 \
    DOTNET_USE_POLLING_FILE_WATCHER=true

# Install only .NET 10 runtime with minimal dependencies, clean up thoroughly
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    dotnet-runtime-10.0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    touch /.dockerenv
