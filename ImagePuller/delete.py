#!/usr/bin/env python3
import sys
import requests

def parse_image(image):
    """
    解析形如 <domain>/<repo>:<tag> 的镜像名称，
    如果 tag 未指定则默认使用 latest。
    """
    if ':' in image:
        image_part, tag = image.rsplit(':', 1)
    else:
        image_part = image
        tag = "latest"
    if '/' not in image_part:
        print("Error: Image name must be in the format <domain>/<repo>:<tag>")
        sys.exit(1)
    parts = image_part.split('/')
    domain = parts[0]
    repository = '/'.join(parts[1:])

    return domain, repository, tag

def get_digest(domain, repository, tag):
    """
    通过调用 /v2/<repo>/manifests/<tag> 接口，并指定 Accept 头
    获取镜像对应的 Docker-Content-Digest，用于删除。
    """
    url = f"http://{domain}/v2/{repository}/manifests/{tag}"
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'}
    print(f"Fetching manifest from {url} ...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error: Unable to fetch manifest. Status code: {response.status_code}. Will try to directly delete the manifest.")
        delete_manifest(domain, repository, tag)
        
    digest = response.headers.get('Docker-Content-Digest')
    if not digest:
        print("Error: Docker-Content-Digest header not found in response.")
        sys.exit(1)
    return digest

def delete_manifest(domain, repository, digest):
    """
    调用 DELETE 接口删除镜像对应的 manifest。
    """
    url = f"http://{domain}/v2/{repository}/manifests/{digest}"
    print(f"Deleting manifest at {url} ...")
    response = requests.delete(url, headers={
        'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json'
    })
    if response.status_code == 202:
        print("Deletion successful.")
    else:
        print(f"Error: Deletion failed with status code: {response.status_code}")
        print(response.text)
        sys.exit(1)

def main():
    if len(sys.argv) != 2:
        print("Usage: python ./delete.py <domain>/<repo>:<tag>")
        sys.exit(1)
    image = sys.argv[1]
    domain, repository, tag = parse_image(image)
    print(f"Processing image: {domain}/{repository}:{tag}")
    digest = get_digest(domain, repository, tag)
    print(f"Found digest: {digest}")
    delete_manifest(domain, repository, digest)

if __name__ == '__main__':
    main()
