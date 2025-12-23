#!/usr/bin/env python3
import sys
import os
import requests

def check_image(image):
    """
    Check if the image is a valid registry image.
    Image format should be <MIRROR_TARGET>/<repository>:<tag>
    """
    registry = os.environ.get('MIRROR_TARGET', 'hub.aiursoft.com')
    if not image.startswith(f"{registry}/"):
        return False

    try:
        rest = image[len(f"{registry}/"):]
        repository, tag = rest.rsplit(":", 1)
    except ValueError:
        return False

    # Get manifest using tag
    url_tag = f"https://{registry}/v2/{repository}/manifests/{tag}"
    resp = requests.get(url_tag, headers={
        'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
    })
    if not resp.ok:
        return False

    try:
        data = resp.json()
    except Exception:
        return False

    # If response contains "manifests" field, verify using digest
    if "manifests" in data:
        try:
            digest = data["manifests"][0]["digest"]
        except (IndexError, KeyError):
            return False

        url_digest = f"https://{registry}/v2/{repository}/manifests/{digest}"
        resp_digest = requests.get(url_digest, headers={
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
        })
        if not resp_digest.ok:
            return False

    # Valid if contains manifests (multi-arch) or layers (single-arch)
    return "manifests" in data or "layers" in data

def main():
    if len(sys.argv) < 2:
        sys.exit(2)

    image = sys.argv[1]
    sys.exit(0 if check_image(image) else 1)

if __name__ == '__main__':
    main()
