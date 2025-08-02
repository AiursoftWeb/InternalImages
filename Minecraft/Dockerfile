ARG VERSION="1.19.3"

#============================
#       Builder image
#============================
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu AS minecraft-builder
ARG VERSION
WORKDIR /app

RUN apt-get update
RUN apt-get install -y curl wget jq unzip

RUN mkdir -p /app/plugins && \
    mkdir -p /app/world && \
    mkdir -p /app/world/datapacks && \
    mkdir -p /app/world_nether && \
    mkdir -p /app/world_the_end && \
    mkdir -p /app/logs

# Accept the EULA
RUN echo "eula=true" > /app/eula.txt

# Config files
COPY ./bukkit.yml /app/bukkit.yml
COPY ./server.properties /app/server.properties
COPY ./ops.json /app/ops.json

# Download Paper MC
RUN buildId=$(curl "https://api.papermc.io/v2/projects/paper/versions/${VERSION}/builds" | jq -r '.builds[-1].build') && \
    url=https://api.papermc.io/v2/projects/paper/versions/${VERSION}/builds/$buildId/downloads/paper-${VERSION}-$buildId.jar && \
    echo "Downloading new Paper MC binary $url" && \
    wget -O /app/papermc.jar $url

# Plugins
# ================
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

# Datapacks
# ================
RUN mkdir /datapacks
RUN touch /datapacks/README.md

# DungeonNowLoading
COPY ./dungeon-now-loading-18.2-v1.19.4.zip /tmp/dnl.zip
RUN unzip /tmp/dnl.zip -d /datapacks/dungeon-now-loading

# BlazeandCave's Advancements Pack
RUN wget -O /tmp/bap.zip "https://mediafilez.forgecdn.net/files/4366/827/BlazeandCave%27s Advancements Pack 1.15.3.zip"
RUN unzip /tmp/bap.zip -d /datapacks/BlazeandCavesAdvancementsPack

# Keepin
#RUN wget -O /tmp/kpin.zip "https://www.planetminecraft.com/data-pack/keepin-keep-inventory-but-lose-all-xp-upon-death/download/file/15192932/"
#RUN unzip /tmp/kpin.zip -d /datapacks/kpin

# Incendium
RUN wget -O /tmp/inc.zip -L "https://www.stardustlabs.net/s/Incendium_1193_v516.zip"
RUN unzip /tmp/inc.zip -d /datapacks/incendium

# Nullscape
RUN wget -O /tmp/nsp.zip -L "https://www.stardustlabs.net/s/Nullscape_1193_v122.zip"
RUN unzip /tmp/nsp.zip -d /datapacks/nullscape

# Terralith
RUN wget -O /tmp/tra.zip -L "https://www.stardustlabs.net/s/Terralith_1193_v2312.zip"
RUN unzip /tmp/tra.zip -d /datapacks/terralith

# Structory_1193_v131a
RUN wget -O /tmp/sty.zip -L "https://www.stardustlabs.net/s/Structory_1193_v131a.zip"
RUN unzip /tmp/sty.zip -d /datapacks/structory

# Ships out of the ocean
#RUN wget -O /tmp/soo.zip -L "https://www.planetminecraft.com/data-pack/ships-out-on-the-oceans/download/file/13598682/"
#RUN unzip /tmp/soo.zip -d /datapacks/soo

# Tree capitator
#RUN wget -O /tmp/tcr.zip -L "https://www.planetminecraft.com/data-pack/treecapitator-datapack-1-13/download/file/16542907/"
#RUN unzip /tmp/tcr.zip -d /datapacks/tcr

#============================
#       lazyMC Builder
#============================
FROM hub.aiursoft.cn/golang:1.21.5 AS lazymc-builder
WORKDIR /src
# 将 lazymc.go 放置在与 Dockerfile 同目录
COPY lazymc.go .

# Create go.mod
RUN go mod init lazymc
# go get github.com/mcstatus-io/mcutil/v4
RUN go get github.com/mcstatus-io/mcutil/v4
RUN go build -o lazymc .


#============================
#       Final image
#============================
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /app

COPY --from=minecraft-builder /app /app
COPY --from=minecraft-builder /datapacks /datapacks
COPY init-commands.sh /app/init-commands.sh

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl wget jq unzip openjdk-24-jre-headless tmux && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/log/mc && \
    touch /var/log/mc/mc.log

# 将 lazymc 二进制拷贝到镜像中
COPY --from=lazymc-builder /src/lazymc /app/lazymc

VOLUME /app/world
VOLUME /app/world_nether
VOLUME /app/world_the_end
VOLUME /app/plugins/dynmap
VOLUME /var/log/mc

EXPOSE 25565
EXPOSE 8123

# Run paper once to download the latest version
RUN java -jar /app/papermc.jar --nojline --nogui --version

# ENTRYPOINT [ "sh", "-c", \
#  "cp -r /datapacks/* /app/world/datapacks/ && \
#  tmux new-session -d -s mc 'java -XX:+UseG1GC -Xms4G -Xmx12G -jar /app/papermc.jar --nojline --nogui > /var/log/mc/mc.log 2>&1' \
#  & tail -f /var/log/mc/mc.log \
#  & sleep 60 && bash /app/init-commands.sh \
#  & wait" ]

ENTRYPOINT ["sh", "-c", \
    "cp -r /datapacks/* /app/world/datapacks/ && /app/lazymc"]