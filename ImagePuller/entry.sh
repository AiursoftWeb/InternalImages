#!/bin/bash
set -e

cd /app

try_docker_login() {
    # Load DOCKER_USERNAME from environment variable
    # Load DOCKER_PASSWORD from /run/secrets/docker-password
    # If any of those not set, do not login
    echo "Attempting to login to Docker Hub..."
    echo "Docker USERNAME: $DOCKER_USERNAME"
    DOCKER_PASSWORD=$(cat /run/secrets/DOCKER_PASSWORD 2>/dev/null || echo "")

    if [[ -z "$DOCKER_USERNAME" || -z "$DOCKER_PASSWORD" ]]; then
        echo ">>> Docker credentials are not set. Skipping login."
        return 0
    fi

    echo ">>> Docker credentials are set. Attempting login..."
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
}

actual_mirror_docker() {
    sourceImage="$1"
    attempt="$2"

    if [[ "$sourceImage" != *":"* ]]; then
        sourceImage="${sourceImage}:latest"
    fi

    imageName=$(echo "$sourceImage" | cut -d: -f1)
    imageTag=$(echo "$sourceImage" | cut -d: -f2)
    finalMirror="hub.aiursoft.cn/${imageName}:${imageTag}"

    echo ">>> Checking if $sourceImage is already mirrored to $finalMirror"
    if python3 is_latest.py "$sourceImage"; then
        echo ">>> Image $sourceImage is already mirrored to $finalMirror. Will check integrity..."
        if ! python3 check.py "$finalMirror"; then
            echo ">>> Integrity check failed for $finalMirror. Attempting to delete..."
            python3 delete.py "$finalMirror"
            return 1
        fi
        echo ">>> Image $finalMirror is valid. Skipping..."
        return 0
    fi

    # If first attempt, use
    if [[ $attempt -eq 1 ]]; then
        /usr/local/bin/regctl image copy "$sourceImage" "$finalMirror" --digest-tags
    else
        # If second or more attempts, use --force-recursive
        /usr/local/bin/regctl image copy "$sourceImage" "$finalMirror" --force-recursive --digest-tags
    fi
    sleep 3

    echo ">>> Image $sourceImage copied to $finalMirror. Checking integrity..."
    
    # First check - manifest via regctl
    if ! /usr/local/bin/regctl image manifest "$finalMirror" &> /dev/null; then
        echo ">>> Manifest check failed for $finalMirror. Attempting to delete..."
        python3 delete.py "$finalMirror"
        return 1
    fi
    
    if ! python3 check.py "$finalMirror"; then
        echo ">>> Health check failed for $finalMirror. Attempting to delete..."
        python3 delete.py "$finalMirror"
        return 1
    fi

    echo ">>> Image $finalMirror is valid. Proceeding to push..."
    return 0
}

mirror_docker() {
    sourceImage="$1"
    max_attempts=8
    
    for attempt in $(seq 1 $max_attempts); do
        echo ">>> Attempting $attempt/$max_attempts: $sourceImage"
        
        if actual_mirror_docker "$sourceImage" "$attempt"; then
            echo ">>> Image $sourceImage mirrored successfully."
            return 0
        fi
        
        # Calculate backoff time with exponential increase and some randomness
        backoff=$((300 + (attempt * attempt * 15) + (RANDOM % 30)))
        
        if [ $attempt -lt $max_attempts ]; then
            echo ">>> Image $sourceImage failed to mirror. Retrying in $backoff seconds..."
            sleep $backoff
        else
            echo ">>> Image $sourceImage failed to mirror after $max_attempts attempts. Skipping..."
            return 1
        fi
    done
}

try_docker_login
mirror_docker "24oi/oi-wiki"
mirror_docker "alpine"
mirror_docker "andyzhangx/samba:win-fix"
mirror_docker "artalk/artalk-go"
mirror_docker "bitwardenrs/server"
mirror_docker "busybox"
mirror_docker "bytemark/webdav"
mirror_docker "caddy"
mirror_docker "caddy:builder"
mirror_docker "clickhouse/clickhouse-server"
mirror_docker "collabora/code"
mirror_docker "consul:1.15.4"
mirror_docker "containrrr/watchtower"
mirror_docker "couchdb"
mirror_docker "couchdb:2.3.0"
mirror_docker "debian:12"
mirror_docker "debian:12.4"
mirror_docker "debian:stable-slim"
mirror_docker "dockurr/windows"
mirror_docker "dperson/samba"
mirror_docker "edgeneko/neko-image-gallery:edge-cpu"
mirror_docker "edgeneko/neko-image-gallery:edge-cuda"
mirror_docker "elasticsearch:8.11.3"
mirror_docker "filebrowser/filebrowser"
mirror_docker "frolvlad/alpine-gxx"
mirror_docker "gcc"
mirror_docker "gcc:4.9.4"
mirror_docker "ghcr.io/anduin2017/how-to-cook:latest"
mirror_docker "ghcr.io/immich-app/immich-machine-learning:release"
mirror_docker "ghcr.io/immich-app/immich-server:release"
mirror_docker "ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0"
mirror_docker "ghcr.io/open-webui/mcpo:main"
mirror_docker "ghcr.io/open-webui/open-webui:main"
mirror_docker "ghcr.io/thomiceli/opengist"
mirror_docker "ghcr.io/usememos/memos"
mirror_docker "ghcr.io/goauthentik/server:2025.6"
mirror_docker "ghcr.io/goauthentik/proxy:2025.6"
mirror_docker "gitea/gitea"
mirror_docker "gitlab/gitlab-ce"
mirror_docker "gitlab/gitlab-ee"
mirror_docker "golang"
mirror_docker "golang:1.21.5"
mirror_docker "grafana/grafana"
mirror_docker "haproxy"
mirror_docker "haskell"
mirror_docker "haskell:9.8.1"
mirror_docker "hello-world"
mirror_docker "homeassistant/home-assistant"
mirror_docker "httpd"
mirror_docker "immybot/remotely"
mirror_docker "immybot/remotely:69"
mirror_docker "immybot/remotely:88"
mirror_docker "imolein/lua:5.4"
mirror_docker "influxdb"
mirror_docker "influxdb:1.8"
mirror_docker "indexyz/mikutap"
mirror_docker "jellyfin/jellyfin"
mirror_docker "jgraph/drawio:24.7.17"
mirror_docker "joxit/docker-registry-ui"
mirror_docker "jvmilazz0/kavita"
mirror_docker "loicsharma/baget"
mirror_docker "louislam/uptime-kuma"
mirror_docker "mariadb"
mirror_docker "mcr.microsoft.com/azuredataexplorer/kustainer-linux"
mirror_docker "mcr.microsoft.com/dotnet/aspnet:6.0"
mirror_docker "mcr.microsoft.com/dotnet/aspnet:7.0"
mirror_docker "mcr.microsoft.com/dotnet/aspnet:8.0"
mirror_docker "mcr.microsoft.com/dotnet/aspnet:9.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:6.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:7.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:8.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:9.0"
mirror_docker "mcr.microsoft.com/mssql/server"
mirror_docker "mcr.microsoft.com/powershell"
mirror_docker "mediawiki"
mirror_docker "mediacms/mediacms"
mirror_docker "memcached"
mirror_docker "mongo"
mirror_docker "mysql"
mirror_docker "neosmemo/memos"
mirror_docker "nextcloud"
mirror_docker "nextcloud:27.1.0"
mirror_docker "nextcloud:31.0.4"
mirror_docker "nextcloud:production"
mirror_docker "nextcloud:stable"
mirror_docker "nginx"
mirror_docker "nginx:alpine"
mirror_docker "node"
mirror_docker "node:16-alpine"
mirror_docker "node:21-alpine"
mirror_docker "nvidia/cuda:11.6.2-base-ubuntu20.04"
mirror_docker "nvidia/cuda:11.8.0-devel-ubuntu22.04"
mirror_docker "nvidia/cuda:12.6.2-devel-ubuntu24.04"
mirror_docker "nvidia/cuda:12.8.1-devel-ubuntu24.04"
mirror_docker "ollama/ollama"
mirror_docker "openjdk:23-jdk"
mirror_docker "oven/bun:slim"
mirror_docker "owncast/owncast"
mirror_docker "passivelemon/terraria-docker"
mirror_docker "perl:5.39.5"
mirror_docker "phanan/koel"
mirror_docker "php:8.3.0-zts"
mirror_docker "portainer/portainer-ce"
mirror_docker "postgres"
mirror_docker "postgres:16-alpine"
mirror_docker "postgres:14-alpine"
mirror_docker "postgres:15.2-alpine"
mirror_docker "prom/prometheus"
mirror_docker "pytorch/pytorch:2.3.0-cuda11.8-cudnn8-devel"
mirror_docker "pytorch/pytorch:2.7.0-cuda12.6-cudnn9-devel"
mirror_docker "python:3.10"
mirror_docker "python:3.11"
mirror_docker "qdrant/qdrant"
mirror_docker "rabbitmq"
mirror_docker "redis"
mirror_docker "redis:7-alpine"
mirror_docker "redis:alpine"
mirror_docker "registry:2"
mirror_docker "rigetti/lisp"
mirror_docker "ruby:3.2.2"
mirror_docker "rust"
mirror_docker "rust:1.81-slim"
mirror_docker "rust:slim"
mirror_docker "rustdesk/rustdesk-server:latest"
mirror_docker "sameersbn/apt-cacher-ng"
mirror_docker "snowdreamtech/frpc"
mirror_docker "snowdreamtech/frps"
mirror_docker "swarmpit/agent"
mirror_docker "swarmpit/swarmpit"
mirror_docker "swift:5.8.1"
mirror_docker "teddysun/xray"
mirror_docker "telegraf"
mirror_docker "thedaviddelta/lingva-translate"
mirror_docker "traefik"
mirror_docker "ubuntu:22.04"
mirror_docker "ubuntu:24.04"
mirror_docker "ubuntu:24.10"
mirror_docker "ubuntu:25.04"
mirror_docker "valkey/valkey:8-bookworm"
mirror_docker "verdaccio/verdaccio"
mirror_docker "vikunja/vikunja"
mirror_docker "vminnovations/typescript-sdk:16-latest"
mirror_docker "wordpress:php8.3-fpm-alpine"

echo "All images are pulled and pushed to the mirror."
