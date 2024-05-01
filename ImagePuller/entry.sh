#!/bin/bash

mirror_docker()
{
    containerName=$1

    if [[ $containerName != *":"* ]]; then
        containerName="$containerName:latest"
    fi
    echo "Container name: $containerName"

    docker pull $containerName
    docker rmi hub.aiursoft.cn/$containerName
    docker tag $containerName hub.aiursoft.cn/$containerName
    docker push hub.aiursoft.cn/$containerName
}

mirror_docker "alpine"
mirror_docker "artalk/artalk-go"
mirror_docker "bitwardenrs/server"
mirror_docker "busybox"
mirror_docker "caddy"
mirror_docker "caddy:builder"
mirror_docker "consul:1.15.4"
mirror_docker "couchdb"
mirror_docker "couchdb:2.3.0"
mirror_docker "debian:12"
mirror_docker "debian:12.4"
mirror_docker "elasticsearch:8.11.3"
mirror_docker "edgeneko/neko-image-gallery:latest"
mirror_docker "edgeneko/neko-image-gallery:latest-cpu"
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
mirror_docker "mcr.microsoft.com/dotnet/sdk:6.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:7.0"
mirror_docker "mcr.microsoft.com/dotnet/sdk:8.0"
mirror_docker "mcr.microsoft.com/mssql/server"
mirror_docker "mcr.microsoft.com/powershell"
mirror_docker "mediacms/mediacms"
mirror_docker "mediawiki"
mirror_docker "memcached"
mirror_docker "mongo"
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
mirror_docker "openjdk:23-jdk"
mirror_docker "openjdk:8-jdk"
mirror_docker "owncast/owncast"
mirror_docker "perl:5.39.5"
mirror_docker "phanan/koel"
mirror_docker "php:8.3.0-zts"
mirror_docker "portainer/portainer-ce"
mirror_docker "postgres"
mirror_docker "postgres:14-alpine"
mirror_docker "postgres:15.2-alpine"
mirror_docker "prom/prometheus"
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
mirror_docker "rust:1.74.1"
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
mirror_docker "ubuntu:20.04"
mirror_docker "ubuntu:22.04"
mirror_docker "ubuntu:24.04"
mirror_docker "vminnovations/typescript-sdk:16-latest"
mirror_docker "wordpress:php8.3-fpm-alpine"

echo "All images are pulled and pushed to the mirror."
echo "Sleeping for 100 seconds to wait for new containers to be started."
sleep 100 # Wait for new images to be pulled

# Get the nextcloud container ID
echo "Upgrading nextcloud..."
containerID=$(docker ps | grep "nextcloud:stable" | awk '{print $1}')
docker exec --user www-data $containerID php occ upgrade