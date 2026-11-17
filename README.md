# Aiursoft InternalImages

## Overview

### What is InternalImages?

InternalImages contains the Docker build contexts for Aiursoft's internal base images and application images. The release pipeline publishes to the internal home registry. The collection includes AnduinOS/.NET/CUDA bases, model services, infrastructure helpers and scheduled workers.

Each directory is an independent build context, not a service in one shared application. Choose the image, CPU architecture, configuration and persistent mounts required for that workload. The source Dockerfiles and existing component documents define its behavior.

## Installation

Install Docker for the intended Linux host and ensure it can reach the selected registry. GPU images additionally require a compatible NVIDIA driver and container runtime on that host. Registry access does not remove the image's runtime hardware or external-service requirements.

Authenticate with an account allowed to pull the internal images:

```bash
docker login hub.aiursoft.com
```

Pull a selected image:

```bash
docker pull hub.aiursoft.com/aiursoft/internalimages/dotnetonlyruntime:latest
```

Internal release tags use `hub.aiursoft.com/aiursoft/internalimages/<image>:latest`. These paths are internal registry targets, not Docker Hub installation paths.

The catalog below describes the configured release jobs, not a live registry availability check. `latest` is mutable; inspect the pulled digest when recording a deployment. Availability for an architecture is limited to that image's configured platforms.

## Usage

### Image catalog

The release jobs in [`.gitlab-ci.yml`](.gitlab-ci.yml) define these image names and build platforms. Image links open the corresponding build-context Dockerfile; all platforms below are Linux:

| Image | CI platforms | Purpose |
| --- | --- | --- |
| [`anduinos-internal`](AnduinOS-Internal/Dockerfile) | amd64, arm64 | AnduinOS base with common command-line and package tools. |
| [`anduinos-with-docker`](AnduinOS-with-docker/Dockerfile) | amd64, arm64 | Internal AnduinOS base with the Docker CLI/package. |
| [`exp-ppa-mirror`](ExpPpaMirror/Dockerfile) | amd64, arm64 | Static mirror/cache service with scheduled APT metadata cleanup. |
| [`lab`](Lab/Dockerfile) | amd64, arm64 | Browser terminal with a demo account and passwordless sudo. |
| [`kiwix`](Kiwix/Dockerfile) | amd64, arm64 | Offline ZIM document server. |
| [`dotnet`](Dotnet/Dockerfile) | amd64, arm64 | .NET 10 SDK and Node.js 24 build environment. |
| [`dotnetonlyruntime`](DotnetOnlyRuntime/Dockerfile) | amd64, arm64 | .NET 10 and ASP.NET Core runtime environment. |
| [`gitmirror`](GitMirror/Dockerfile) | amd64, arm64 | Scheduled GitLab-to-GitHub repository mirror. |
| [`minecraft`](Minecraft/Dockerfile) | amd64, arm64 | Paper server with bundled plugins and datapacks. |
| [`nvidia`](Nvidia/Dockerfile) | amd64 | CUDA development base for GPU images. |
| [`swinir`](SwinIR/Dockerfile) | amd64 | Batch image super-resolution with a baked model. |
| [`youtubedl`](Youtubedl/Dockerfile) | amd64, arm64 | Scheduled yt-dlp downloads with persistent archive and cookies. |
| [`reportertts`](ReporterTTS/Dockerfile) | amd64 | IndexTTS speech service with model weights and persistent data. |
| [`paddleocr`](PaddleOCR/Dockerfile) | amd64 | CPU OCR service with warmed model cache. |
| [`codexproxy`](CodexProxy/Dockerfile) | amd64 | Packaged local proxy source with authentication/startup patches. |
| [`gitlab-ci-collector`](GitLabCiCollector/Dockerfile) | amd64, arm64 | GitLab CI event collection into ClickHouse. |
| [`mcpo`](MCPO/Dockerfile) | amd64, arm64 | Open WebUI MCP-to-OpenAPI proxy with dependency/runtime updates. |
| [`badge-proxy`](BadgeProxy/Dockerfile) | amd64, arm64 | GitLab pipeline and coverage badge service. |

[FunASR](FunASR/Dockerfile) and [FunASRRealtime](FunASRRealtime/Dockerfile) also have source build contexts, but no corresponding deploy jobs in the current pipeline. Their directories alone do not establish an automatically published image or a supported release-platform list.

### Run an image

For example, inspect the .NET runtime image without mounting host data:

```bash
docker run --rm hub.aiursoft.com/aiursoft/internalimages/dotnetonlyruntime:latest \
  dotnet --info
```

The command should list the installed runtime environment; this image does not include the SDK. Use `dotnet` for SDK/build workloads. These base images do not start your application automatically: supply the application files and command in the consuming Dockerfile or deployment.

Application images need their own ports, credentials, permissions and persistent storage. `Lab` exposes a browser shell with a demo account and passwordless sudo; keep it behind an appropriate access boundary. `GitMirror` force-aligns its dedicated repository checkout and force-pushes configured mirrors; do not point its persistent workspace at a developer's working tree.

For a long-running container, inspect its logs and health state as well as the application-specific result. Preserve persistent mounts when replacing a container. Publishing a new image does not prove that a consuming Box has pulled, deployed or passed health checks with that image.

## Configuration

The .NET images declare these container defaults in their Dockerfiles:

| Variable | Default | Applies to |
| --- | --- | --- |
| `ASPNETCORE_ENVIRONMENT` | `Production` | Both .NET images |
| `DOTNET_CLI_TELEMETRY_OPTOUT` | `1` | Both .NET images |
| `DOTNET_PRINT_TELEMETRY_MESSAGE` | `false` | Both .NET images |
| `ASPNETCORE_FORWARDEDHEADERS_ENABLED` | `true` | Both .NET images |
| `DOTNET_RUNNING_IN_CONTAINER` | `true` | Both .NET images |
| `DOTNET_GENERATE_ASPNET_CERTIFICATE` | `false` | Both .NET images |
| `DOTNET_NOLOGO` | `true` | Both .NET images |
| `ASPNETCORE_HTTP_PORTS` | `5000` | Both .NET images |
| `DOTNET_USE_POLLING_FILE_WATCHER` | `true` | Both .NET images |
| `NUGET_XMLDOC_MODE` | `skip` | SDK image only |

A consuming Dockerfile or runtime environment can override image environment defaults. Declaring an application port does not publish it on the host; the deployment must configure its own network mapping. Application settings and credentials belong to the consuming service, not to one shared configuration for this collection.

Other image-specific inputs include:

| Image or context | Configuration and persistent state |
| --- | --- |
| `anduinos-internal` | Tracked [Ubuntu APT source configuration](AnduinOS-Internal/ubuntu.sources). |
| `anduinos-with-docker` | Adds Docker tooling; no host Docker socket is mounted automatically. |
| `exp-ppa-mirror` | [Static mirror entry point](ExpPpaMirror/entrypoint.sh) and scheduled [metadata cleanup](ExpPpaMirror/cleanup.sh); preserve its `/data` cache. |
| `kiwix` | Mount the selected `.zim` files under `/data`; the server listens on container port `8080`. |
| `gitmirror` | Persistent `/opt/Source/Repos` workspace and `/run/secrets/github-token`; [mirror.sh](GitMirror/mirror.sh) defines source selection, force updates and destination mapping. |
| `minecraft` | `VERSION` build argument defaults to `1.19.3`, but the bundled server JAR determines the actual version and changing that argument alone does not replace it; tracked [server properties](Minecraft/server.properties), plugins, worlds, Dynmap data and logs define the server state. The Dockerfile accepts the Minecraft EULA during build. |
| `youtubedl` | Scheduled channel list in [entry.sh](Youtubedl/entry.sh); `/mnt/data/youtube/cookies.txt` is required and download history/output live under `/mnt/data`. |
| `swinir` | `SCALE=4`, `TILE=192`, `TILE_OVERLAP=16`; input `/app/input`, output `/app/results/swinir_real_sr_x4_large`. |
| `reportertts` | `TTS_ACCESS_TOKEN`, queue/cache/model settings and persistent `/data`; defaults and limits are in [main.py](ReporterTTS/main.py). |
| `paddleocr` | `OCR_ACCESS_TOKEN`, `MAX_PDF_PAGES` and OCR routes in [main.py](PaddleOCR/main.py). |
| `codexproxy` | Authentication import, persistent login directory and startup patches; see [CodexProxy](CodexProxy/README.md) and [entry point](CodexProxy/docker-entrypoint.sh). |
| `gitlab-ci-collector` | GitLab/ClickHouse credentials and source selection; see [collector configuration](GitLabCiCollector/README.md). |
| `badge-proxy` | GitLab read-only API access and public badge endpoints; see [BadgeProxy](BadgeProxy/README.md). |
| `mcpo` | Inherits the base proxy's command/configuration; [the Dockerfile](MCPO/Dockerfile) applies the dependency/runtime updates. |
| `FunASR` / `FunASRRealtime` | Model, token, device and port inputs are declared in their [HTTP](FunASR/Dockerfile) and [WebSocket](FunASRRealtime/Dockerfile) build contexts; no release job is configured. |

GPU/model images can download substantial dependencies and model files during build. Use the per-image platform and hardware requirements; the presence of model files does not imply an enforced GPU-memory limit. Keep service credentials and persistent authentication state outside the source repository.

**Release configuration.** The existing pipeline selects `aiur-global-builder` and requires the `aiursoft` project namespace. `LOCAL_DOCKER_USERNAME` and `LOCAL_DOCKER_PASSWORD` authenticate to `hub.aiursoft.com`. Jobs set `IMAGE_NAME`, `CONTEXT` and optional `PLATFORMS`; the target uses the project's namespace/name plus the image name. These are CI variables, not application runtime variables. Configure credentials through the existing private CI settings; do not put them in Dockerfiles or command examples.

## Development

Fetch the source and work in the repository root:

```bash
git clone https://gitlab.aiursoft.com/aiursoft/internalimages.git
cd internalimages
```

Build using the repository's standard build entry point:

```bash
docker buildx build --platform linux/amd64 --load \
  -t local/dotnetonlyruntime:dev ./DotnetOnlyRuntime
```

The build context is the selected image directory. This example loads one local image and does not publish it. Docker Buildx and access to the Dockerfile's base images and package/model sources are required; several contexts use internal base images even in ExternalImages. For multi-platform release builds, use the existing configured builder and the platform list from the release job.

The existing `test_codexproxy` job runs the patched, installed proxy package's server/translator/Responses tests and its startup tests in separate Python processes. Follow [the component test guide](CodexProxy/README.md); installing the unpatched source alone does not reproduce the CI contract. The job runs for merge requests and on `master`, and `deploy_codexproxy` waits for it. Other component checks live alongside their own sources.

Publish the verified artifacts using the existing release workflow:

After a reviewed change reaches `master`, the deploy jobs build and push `latest` to the internal registry. The current deploy template runs on `master` without path-based change filters, so even a README-only merge uses the normal full release job set. Existing `needs` relationships order base-image consumers, and the CodexProxy image also requires its test job.

Image publication and deployment to a running Box are separate steps. Do not change shared registry credentials, builder configuration or publication rules as part of adding a documentation example.

## Documentation

- [BadgeProxy](BadgeProxy/README.md)
- [CodexProxy](CodexProxy/README.md)
- [GitLabCiCollector](GitLabCiCollector/README.md)

Keep each component's detailed configuration, authentication, storage, recovery and testing instructions in its existing document. This root README provides the collection-level entry point; it does not replace those documents.

## How to contribute

There are many ways to contribute to the project: logging bugs, submitting pull requests, reporting issues, and creating suggestions.

Even if you have push rights on the repository, you should create a personal fork and create feature branches there when you need them. This keeps the main repository clean and your workflow cruft out of sight.

We're also interested in your feedback on the future of this project. You can submit a suggestion or feature request through the issue tracker. To make this process more effective, we're asking that these include more information to help define them more clearly.

## License

This repository does not currently declare a collection-wide license in a root LICENSE file. Individual bundled projects and image layers retain their own upstream licenses and notices; inspect the selected component before redistribution. Do not assume one license applies to every image in this collection.
