#============================
#       Builder image
#============================
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu as minecraft-builder
WORKDIR /app

RUN apt update
RUN apt install -y curl wget jq

RUN mkdir -p /app/plugins && \
    mkdir -p /app/world && \
    mkdir -p /app/world_nether && \
    mkdir -p /app/world_the_end && \
    mkdir -p /app/logs

# Accept the EULA
RUN echo "eula=true" > /app/eula.txt

# Config files
COPY ./bukkit.yml /app/bukkit.yml
COPY ./server.properties /app/server.properties
COPY ./ops.json /app/ops.json

RUN buildId=$(curl 'https://api.papermc.io/v2/projects/paper/versions/1.19.3/builds' | jq -r '.builds[-1].build') && \
    url=https://api.papermc.io/v2/projects/paper/versions/1.19.3/builds/$buildId/downloads/paper-1.19.3-$buildId.jar && \
    echo "Downloading new Paper MC binary $url" && \
    wget -O /app/papermc.jar $url

# Geyser-Spigot
RUN wget -O /app/plugins/Geyser-Spigot.jar "https://download.geysermc.org/v2/projects/geyser/versions/latest/builds/latest/downloads/spigot"

# floodgate-spigot
RUN wget -O /app/plugins/floodgate-spigot.jar "https://download.geysermc.org/v2/projects/floodgate/versions/latest/builds/latest/downloads/spigot"

# ViaBackwards
RUN viabUrl=$(curl https://api.github.com/repos/ViaVersion/ViaBackwards/releases/latest | jq -r '(.assets[] | select(.browser_download_url | contains(".jar"))).browser_download_url') && \
    wget -O /app/plugins/ViaBackwards.jar $viabUrl

# ViaVersion
RUN viavUrl=$(curl https://api.github.com/repos/ViaVersion/ViaVersion/releases/latest | jq -r '(.assets[] | select(.browser_download_url | contains(".jar"))).browser_download_url') && \
    wget -O /app/plugins/ViaVersion.jar $viavUrl

# Dynmap
RUN wget -O /app/plugins/Dynmap.jar "https://dev.bukkit.org/projects/dynmap/files/latest"

# NoEndermanGrief
RUN wget -O /app/plugins/NoEndermanGrief.jar "https://dev.bukkit.org/projects/no-enderman-grief2/files/latest"

# NoBoom
COPY ./NoBoom-1.2.jar /app/plugins/NoBoom.jar

#============================
#       Final image
#============================
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /app

COPY --from=minecraft-builder /app /app

RUN apt update
RUN apt install -y openjdk-17-jre-headless

VOLUME /app/world
VOLUME /app/world_nether
VOLUME /app/world_the_end

EXPOSE 25565
EXPOSE 19132/udp
EXPOSE 8123

ENTRYPOINT [ "/usr/bin/java", "-XX:+UseG1GC", "-Xms6G", "-Xmx13G", "-jar", "/app/papermc.jar", "--nojline", "--nogui" ]