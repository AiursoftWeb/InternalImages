#!/usr/bin/env python3
import sys
import requests

def parse_image(image):
    """
    This function parses the image string to extract the domain, repository, and tag.
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
    Call the GET interface to get the manifest of the image.
    """
    url = f"http://{domain}/v2/{repository}/manifests/{tag}"
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'}
    print(f"Fetching manifest from {url} ...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error: Unable to fetch manifest. Status code: {response.status_code}")
        print("The image may not exist in the registry.")
        sys.exit(1)
        
    digest = response.headers.get('Docker-Content-Digest')
    if not digest:
        print("Error: Docker-Content-Digest header not found in response.")
        sys.exit(1)
    return digest

def delete_manifest(domain, repository, digest):
    """
    Call the DELETE interface to delete the manifest.
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
