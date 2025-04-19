#!/usr/bin/env python3
import sys
import requests

def check_image(image):
    """
    Checking if the image is a valid Aiursoft registry image.
    image format should be：hub.aiursoft.cn/<repository>:<tag>
    """
    registry = "hub.aiursoft.cn"
    if not image.startswith(f"{registry}/"):
        print("Image doesn't belong to registry", file=sys.stderr)
        return False

    try:
        rest = image[len(f"{registry}/"):]
        repository, tag = rest.rsplit(":", 1)
    except ValueError:
        print("Image format error", file=sys.stderr)
        return False

    # Use the tag to get the manifest
    url_tag = f"https://{registry}/v2/{repository}/manifests/{tag}"
    resp = requests.get(url_tag, headers={
        'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
    })
    if not resp.ok:
        print(f"{url_tag} Failed to get manifest: {repository}:{tag}. Status Code: {resp.status_code}", file=sys.stderr)
        return False

    try:
        data = resp.json()
    except Exception as e:
        print("Failed to parse manifest data", file=sys.stderr)
        return False

    # If response contains "manifests" field, it means the image is a multi-arch image
    if "manifests" in data:
        try:
            digest = data["manifests"][0]["digest"]
        except (IndexError, KeyError):
            print("Failed to get digest from manifests", file=sys.stderr)
            return False

        url_digest = f"https://{registry}/v2/{repository}/manifests/{digest}"
        resp_digest = requests.get(url_digest, headers={
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
        })
        if not resp_digest.ok:
            print(f"{url_digest} Failed to get manifest: {repository}:{tag}. Status Code: {resp_digest.status_code}", file=sys.stderr)
            return False

    if "manifests" in data:
        print(f"The manifest data contains the 'manifests' field, indicating that this image is a multi-arch image.", file=sys.stderr)
        return True
    elif "layers" in data:
        print(f"The manifest data does not contain the 'manifests' field but contains the 'layers' field, indicating that this image is a single-arch image.", file=sys.stderr)
        return True
    else:
        print(f"The manifest data does not contain 'manifests' and 'layers' fields. URL: {url_tag}. This means something might be wrong!", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: check.py <image>", file=sys.stderr)
        sys.exit(2)

    image = sys.argv[1]
    if check_image(image):
        print(f"Image {image} is valid", file=sys.stderr)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
