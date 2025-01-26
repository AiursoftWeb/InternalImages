FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu:latest

# Install dotnet, also install curl and wget because they are often used in dotnet containers.
RUN apt update && \
    apt install -y dotnet9 curl wget && \
    apt clean && \
    touch /.dockerenv

# return File.Exists("/.dockerenv") || Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER")?.ToLower().Trim() == "true";


# Configure environment variables
ENV ASPNETCORE_ENVIRONMENT="Production" \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_PRINT_TELEMETRY_MESSAGE="false" \
    ASPNETCORE_FORWARDEDHEADERS_ENABLED="true" \
    DOTNET_RUNNING_IN_CONTAINER="true" \
    DOTNET_NOLOGO="1"

RUN dotnet --info && echo $ASPNETCORE_ENVIRONMENT && \
    echo "Environment setup complete."