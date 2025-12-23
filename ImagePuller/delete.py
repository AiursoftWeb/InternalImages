#!/usr/bin/env python3
import sys
import requests

def parse_image(image):
    """Parse image string to extract domain, repository, and tag."""
    if ':' in image:
        image_part, tag = image.rsplit(':', 1)
    else:
        image_part = image
        tag = "latest"
    if '/' not in image_part:
        sys.exit(1)
    parts = image_part.split('/')
    domain = parts[0]
    repository = '/'.join(parts[1:])
    return domain, repository, tag

def get_digest(domain, repository, tag):
    """Get the manifest digest of the image."""
    url = f"http://{domain}/v2/{repository}/manifests/{tag}"
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        sys.exit(1)
    digest = response.headers.get('Docker-Content-Digest')
    if not digest:
        sys.exit(1)
    return digest

def delete_manifest(domain, repository, digest):
    """Delete the manifest from registry."""
    url = f"http://{domain}/v2/{repository}/manifests/{digest}"
    response = requests.delete(url, headers={
        'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json'
    })
    if response.status_code != 202:
        sys.exit(1)

def main():
    if len(sys.argv) != 2:
        sys.exit(1)
    image = sys.argv[1]
    domain, repository, tag = parse_image(image)
    digest = get_digest(domain, repository, tag)
    delete_manifest(domain, repository, digest)

if __name__ == '__main__':
    main()
