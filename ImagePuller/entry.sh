#!/bin/bash

set -e

prepare_buildx() {
    # 检查是否已经存在 multiarch_builder 构建器
    if docker buildx ls | grep -q multiarch_builder; then
        echo ">>> multiarch_builder 构建器已存在，直接使用"
        docker buildx use multiarch_builder
        return
    else
        echo ">>> 未找到 multiarch_builder 构建器，创建新的构建器"
        docker buildx create --name multiarch_builder
        docker buildx use multiarch_builder
    fi

    echo ">>> 启动 multiarch_builder 构建器"
    docker buildx inspect multiarch_builder --bootstrap
}

actual_mirror_docker() {
    sourceImage="$1"

    if [[ "$sourceImage" != *":"* ]]; then
        sourceImage="${sourceImage}:latest"
    fi

    imageName=$(echo "$sourceImage" | cut -d: -f1)
    imageTag=$(echo "$sourceImage" | cut -d: -f2)
    finalMirror="hub.aiursoft.cn/${imageName}:${imageTag}"

    echo ">>> 镜像转换: $sourceImage --> $finalMirror"

    # Execute the command and capture both its exit status and output
    output=$(docker buildx imagetools create -t "$finalMirror" "$sourceImage" 2>&1)
    status=$?
    
    # Check if rate limit error occurred
    if echo "$output" | grep -q "Too Many Requests"; then
        echo ">>> 遇到速率限制: $output"
        return 1
    fi
    
    # Check for any other errors
    if [ $status -ne 0 ]; then
        echo ">>> 镜像推送失败: $output"
        return 2
    fi

    # Verify the image exists in the local registry
    echo ">>> 验证镜像: $finalMirror"
    if docker manifest inspect "$finalMirror" &> /dev/null; then
        echo ">>> 镜像推送成功: $finalMirror"
        return 0
    else
        echo ">>> 镜像推送验证失败"
        return 3
    fi
}

mirror_docker() {
    sourceImage="$1"
    max_attempts=8
    
    for attempt in $(seq 1 $max_attempts); do
        echo ">>> 尝试 $attempt/$max_attempts: $sourceImage"
        
        if actual_mirror_docker "$sourceImage"; then
            echo ">>> 镜像 $sourceImage 处理完成"
            return 0
        fi
        
        # Calculate backoff time with exponential increase and some randomness
        backoff=$((300 + (attempt * attempt * 150) + (RANDOM % 300)))
        
        if [ $attempt -lt $max_attempts ]; then
            echo ">>> 镜像推送失败，${backoff}秒后重试..."
            sleep $backoff
        else
            echo ">>> 镜像 $sourceImage 处理失败，已达到最大重试次数"
            return 1
        fi
    done
}

prepare_buildx
mirror_docker "alpine"
mirror_docker "andyzhangx/samba:win-fix"
mirror_docker "ghcr.io/anduin2017/how-to-cook:latest"
mirror_docker "artalk/artalk-go"
mirror_docker "bitwardenrs/server"
mirror_docker "busybox"
mirror_docker "caddy"
mirror_docker "caddy:builder"
mirror_docker "clickhouse/clickhouse-server"
mirror_docker "collabora/code"
mirror_docker "consul:1.15.4"
mirror_docker "couchdb"
mirror_docker "couchdb:2.3.0"
mirror_docker "debian:12"
mirror_docker "debian:12.4"
mirror_docker "debian:stable-slim"
mirror_docker "dockurr/windows"
mirror_docker "dperson/samba"
mirror_docker "elasticsearch:8.11.3"
mirror_docker "edgeneko/neko-image-gallery:edge-cuda"
mirror_docker "edgeneko/neko-image-gallery:edge-cpu"
mirror_docker "frolvlad/alpine-gxx"
mirror_docker "filebrowser/filebrowser"
mirror_docker "gcc"
mirror_docker "gcc:4.9.4"
mirror_docker "ghcr.io/thomiceli/opengist"
mirror_docker "ghcr.io/usememos/memos"
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
mirror_docker "jellyfin/jellyfin"
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
mirror_docker "mediacms/mediacms"
mirror_docker "mediawiki"
mirror_docker "memcached"
mirror_docker "mongo"
mirror_docker "nvidia/cuda:11.6.2-base-ubuntu20.04"
mirror_docker "nvidia/cuda:11.8.0-devel-ubuntu22.04"
mirror_docker "indexyz/mikutap"
mirror_docker "mysql"
mirror_docker "nextcloud"
mirror_docker "nextcloud:stable"
mirror_docker "nextcloud:production"
mirror_docker "nextcloud:27.1.0"
mirror_docker "nginx"
mirror_docker "nginx:alpine"
mirror_docker "node"
mirror_docker "node:16-alpine"
mirror_docker "node:21-alpine"
mirror_docker "ollama/ollama"
mirror_docker "openjdk:23-jdk"
mirror_docker "openjdk:8-jdk"
mirror_docker "oven/bun:slim"
mirror_docker "ghcr.io/open-webui/open-webui:main"
mirror_docker "24oi/oi-wiki"
mirror_docker "owncast/owncast"
mirror_docker "passivelemon/terraria-docker"
mirror_docker "perl:5.39.5"
mirror_docker "phanan/koel"
mirror_docker "php:8.3.0-zts"
mirror_docker "portainer/portainer-ce"
mirror_docker "postgres"
mirror_docker "postgres:14-alpine"
mirror_docker "postgres:15.2-alpine"
mirror_docker "prom/prometheus"
mirror_docker "pytorch/pytorch:2.3.0-cuda11.8-cudnn8-devel"
mirror_docker "python:3.10"
mirror_docker "python:3.11"
mirror_docker "qdrant/qdrant"
mirror_docker "rabbitmq"
mirror_docker "redis"
mirror_docker "redis:alpine"
mirror_docker "redis:7-alpine"
mirror_docker "registry:2"
mirror_docker "rigetti/lisp"
mirror_docker "ruby:3.2.2"
mirror_docker "rust"
mirror_docker "rust:slim"
mirror_docker "rust:1.81-slim"
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
mirror_docker "vminnovations/typescript-sdk:16-latest"
mirror_docker "verdaccio/verdaccio"
mirror_docker "wordpress:php8.3-fpm-alpine"
mirror_docker "bytemark/webdav"
mirror_docker "jgraph/drawio:24.7.17"

echo "All images are pulled and pushed to the mirror."
