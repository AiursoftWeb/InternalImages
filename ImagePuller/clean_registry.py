#!/usr/bin/env python3
import requests
import subprocess

# Registry 基本配置
REGISTRY_URL = "https://hub.aiursoft.com"
CATALOG_ENDPOINT = f"{REGISTRY_URL}/v2/_catalog?n=1000"
# 镜像数据在本地存放的路径
BASE_PATH = "/swarm-vol/registry-data/docker/registry/v2/repositories"

def get_repositories():
    response = requests.get(CATALOG_ENDPOINT)
    response.raise_for_status()
    data = response.json()
    return data.get("repositories", [])

def is_invalid_image(repo):
    # 获取镜像 tags 列表
    tags_url = f"{REGISTRY_URL}/v2/{repo}/tags/list"
    response = requests.get(tags_url)
    response.raise_for_status()
    data = response.json()
    # tags 为 None 时认为镜像出错
    return data.get("tags") is None

def remove_repository(repo):
    # 构造镜像对应的目录路径
    repo_path = f"{BASE_PATH}/{repo}"
    cmd = ["sudo", "rm", "-rvf", repo_path]
    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print(f"Removed repository: {repo}")
    except subprocess.CalledProcessError as e:
        print(f"Error removing repository {repo}: {e}")

def main():
    repos = get_repositories()
    for repo in repos:
        if is_invalid_image(repo):
            print(f"Repository '{repo}' is invalid, removing...")
            remove_repository(repo)
        else:
            print(f"Repository '{repo}' is valid.")

if __name__ == '__main__':
    main()
