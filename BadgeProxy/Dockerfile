FROM --platform=$BUILDPLATFORM hub.aiursoft.com/aiursoft/internalimages/dotnet AS build
WORKDIR /src
COPY *.csproj ./
RUN dotnet restore
COPY *.cs ./
RUN dotnet publish -c Release --no-restore -o /app /p:UseAppHost=false

FROM hub.aiursoft.com/aiursoft/internalimages/dotnetonlyruntime:latest
WORKDIR /app
COPY --from=build /app ./
USER 1654:1654
EXPOSE 5000
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 CMD ["dotnet", "BadgeProxy.dll", "--healthcheck"]
ENTRYPOINT ["dotnet", "BadgeProxy.dll"]
