#!/bin/bash
set -e

cd /app

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} ${BOLD}$1${NC}"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} ${BOLD}$1${NC}"
}

log_step() {
    echo -e "\n${CYAN}▶${NC} ${BOLD}$1${NC}"
}

log_detail() {
    echo -e "  ${DIM}$1${NC}"
}

must_login_local_registry() {
    if [[ -z "$MIRROR_TARGET" ]]; then
        log_error "MIRROR_TARGET is not set. Cannot proceed."
        exit 1
    fi

    log_step "Authenticating to local registry"
    log_detail "Registry: ${MIRROR_TARGET}"
    log_detail "Username: ${LOCAL_DOCKER_USERNAME}"

    if [[ -z "$LOCAL_DOCKER_USERNAME" || -z "$LOCAL_DOCKER_PASSWORD" ]]; then
        log_error "Local Docker credentials are not set. Aborting."
        exit 1
    fi

    echo "$LOCAL_DOCKER_PASSWORD" | docker login ${MIRROR_TARGET} -u "$LOCAL_DOCKER_USERNAME" --password-stdin > /dev/null 2>&1
    log_success "Successfully authenticated to ${MIRROR_TARGET}"
}

try_docker_login() {
    log_step "Authenticating to Docker Hub"
    
    if [[ -z "$DOCKER_USERNAME" || -z "$DOCKER_PASSWORD" ]]; then
        log_warning "Docker Hub credentials not set. Skipping authentication."
        return 0
    fi

    log_detail "Username: ${DOCKER_USERNAME}"
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin > /dev/null 2>&1
    log_success "Successfully authenticated to Docker Hub"
}


actual_mirror_docker() {
    sourceImage="$1"
    attempt="$2"

    if [[ "$sourceImage" != *":"* ]]; then
        sourceImage="${sourceImage}:latest"
    fi

    imageName=$(echo "$sourceImage" | cut -d: -f1)
    imageTag=$(echo "$sourceImage" | cut -d: -f2)
    finalMirror="${MIRROR_TARGET}/${imageName}:${imageTag}"

    log_detail "Source: ${sourceImage}"
    log_detail "Target: ${finalMirror}"
    
    # Check if already mirrored
    if python3 is_latest.py "$sourceImage" 2>/dev/null; then
        log_info "Image already mirrored, verifying integrity..."
        if ! python3 check.py "$finalMirror" 2>/dev/null; then
            log_warning "Integrity check failed, cleaning up..."
            python3 delete.py "$finalMirror" 2>/dev/null || true
            return 1
        fi
        log_success "Image is up-to-date and valid"
        return 0
    fi

    # Perform the copy
    log_info "Copying image (attempt ${attempt})..."
    if [[ $attempt -eq 1 ]]; then
        /usr/local/bin/regctl image copy "$sourceImage" "$finalMirror" --digest-tags 2>&1 | sed 's/^/  /'
    else
        /usr/local/bin/regctl image copy "$sourceImage" "$finalMirror" --force-recursive --digest-tags 2>&1 | sed 's/^/  /'
    fi
    sleep 3

    # Verify the copy
    log_info "Verifying mirrored image..."
    
    if ! /usr/local/bin/regctl image manifest "$finalMirror" &> /dev/null; then
        log_error "Manifest verification failed"
        python3 delete.py "$finalMirror" 2>/dev/null || true
        return 1
    fi
    
    if ! python3 check.py "$finalMirror" 2>/dev/null; then
        log_error "Health check failed"
        python3 delete.py "$finalMirror" 2>/dev/null || true
        return 1
    fi

    log_success "Image mirrored and verified successfully"
    return 0
}



mirror_docker() {
    sourceImage="$1"
    max_attempts=8
    
    log_step "Mirroring: ${BOLD}${sourceImage}${NC}"
    
    for attempt in $(seq 1 $max_attempts); do
        log_info "Attempt ${attempt}/${max_attempts}"
        
        if actual_mirror_docker "$sourceImage" "$attempt"; then
            log_success "${BOLD}${sourceImage}${NC} mirrored successfully"
            echo ""
            return 0
        fi
        
        # Calculate backoff time with exponential increase and some randomness
        backoff=$((300 + (attempt * attempt * 15) + (RANDOM % 30)))
        
        if [ $attempt -lt $max_attempts ]; then
            log_warning "Mirror failed, retrying in ${backoff}s..."
            sleep $backoff
        else
            log_error "${BOLD}${sourceImage}${NC} failed after ${max_attempts} attempts"
            echo ""
            return 1
        fi
    done
}


must_login_local_registry
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
mirror_docker "chocobozzz/peertube-webserver"
mirror_docker "chocobozzz/peertube:production-bookworm"
mirror_docker "clickhouse/clickhouse-server"
mirror_docker "cloudflare/cloudflared"
mirror_docker "collabora/code"
mirror_docker "consul:1.15.4"
mirror_docker "containrrr/watchtower"
mirror_docker "containrrr/shepherd"
mirror_docker "couchdb"
mirror_docker "couchdb:2.3.0"
mirror_docker "debian:12"
mirror_docker "debian:12.4"
mirror_docker "debian:stable-slim"
mirror_docker "docker:dind"
mirror_docker "docker:latest"
mirror_docker "docker:dind-rootless"
mirror_docker "dockurr/windows"
mirror_docker "dperson/samba"
mirror_docker "edgeneko/neko-image-gallery:edge-cpu"
mirror_docker "edgeneko/neko-image-gallery:edge-cuda"
mirror_docker "elasticsearch:8.11.3"
mirror_docker "elasticsearch:9.0.4"
mirror_docker "filebrowser/filebrowser"
mirror_docker "frolvlad/alpine-gxx"
mirror_docker "gcc"
mirror_docker "gcc:4.9.4"
mirror_docker "ghcr.io/anduin2017/how-to-cook:latest"
mirror_docker "ghcr.io/caioricciuti/ch-ui:latest"
mirror_docker "ghcr.io/immich-app/immich-machine-learning:release"
mirror_docker "ghcr.io/immich-app/immich-server:release"
mirror_docker "ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0"
mirror_docker "ghcr.io/nextcloud-releases/aio-talk"
mirror_docker "ghcr.io/open-webui/mcpo:main"
mirror_docker "ghcr.io/open-webui/open-webui:main"
mirror_docker "ghcr.io/thomiceli/opengist"
mirror_docker "ghcr.io/usememos/memos"
mirror_docker "ghcr.io/goauthentik/server:2025.10.3"
mirror_docker "ghcr.io/goauthentik/proxy:2025.10.3"
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
mirror_docker "louislam/uptime-kuma:1"
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
mirror_docker "minio/minio"
mirror_docker "mongo"
mirror_docker "mwader/postfix-relay"
mirror_docker "mysql"
mirror_docker "neosmemo/memos:stable"
mirror_docker "nextcloud"
mirror_docker "nextcloud:27.1.0"
mirror_docker "nextcloud:31.0.7"
mirror_docker "nextcloud:production"
mirror_docker "nextcloud:stable"
mirror_docker "nginx"
mirror_docker "nginx:alpine"
mirror_docker "node"
mirror_docker "node:16-alpine"
mirror_docker "node:21-alpine"
mirror_docker "node:22-alpine"
mirror_docker "node:24-alpine"
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
mirror_docker "postgres:13-alpine"
mirror_docker "postgres:14-alpine"
mirror_docker "postgres:15.2-alpine"
mirror_docker "postgres:16-alpine"
mirror_docker "prom/prometheus"
mirror_docker "pytorch/pytorch:2.3.0-cuda11.8-cudnn8-devel"
mirror_docker "pytorch/pytorch:2.7.0-cuda12.6-cudnn9-devel"
mirror_docker "python:3.10"
mirror_docker "python:3.11"
mirror_docker "qdrant/qdrant"
mirror_docker "rabbitmq"
mirror_docker "redis"
mirror_docker "redis:7-alpine"
mirror_docker "redis:6-alpine"
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
mirror_docker "timberio/vector:latest-alpine"
mirror_docker "traefik"
mirror_docker "ubuntu:22.04"
mirror_docker "ubuntu:24.04"
mirror_docker "ubuntu:24.10"
mirror_docker "ubuntu:25.04"
mirror_docker "ubuntu:25.10"
mirror_docker "valkey/valkey:8-bookworm"
mirror_docker "vaultwarden/server"
mirror_docker "vaultwarden/server:testing"
mirror_docker "verdaccio/verdaccio"
mirror_docker "vikunja/vikunja"
mirror_docker "vminnovations/typescript-sdk:16-latest"
mirror_docker "wolveix/satisfactory-server:latest"
mirror_docker "wordpress:php8.3-fpm-alpine"

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log_success "${BOLD}All images have been processed${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
