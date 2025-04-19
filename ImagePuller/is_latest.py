#!/usr/bin/env python3
# filepath: /home/anduin/Source/Repos/Aiursoft/bash-app/InternalImages/ImagePuller/is_latest.py
import sys
import subprocess
import os

def get_mirror_image(source_image):
    """Convert a source image name to its mirror equivalent."""
    if ':' in source_image:
        repo_part, tag = source_image.rsplit(':', 1)
    else:
        repo_part = source_image
        tag = "latest"
    
    # Handle special cases for Docker Hub
    if '/' not in repo_part:
        # Simple Docker Hub image like "nginx"
        mirror_repo = f"{repo_part}"
    else:
        # Keep as is for other registries or namespaced Docker Hub images
        mirror_repo = repo_part
    
    return f"hub.aiursoft.cn/{mirror_repo}:{tag}"

def get_image_digest(image):
    """Get the digest for a Docker image using regctl."""
    try:
        result = subprocess.run(
            ["/usr/local/bin/regctl", "image", "digest", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            print(f"Failed to get digest for {image}: {result.stderr}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error running regctl for {image}: {e}", file=sys.stderr)
        return None

def image_exists(image):
    """Check if an image exists using regctl."""
    try:
        result = subprocess.run(
            ["/usr/local/bin/regctl", "image", "manifest", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        return result.returncode == 0
    except:
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python is_latest.py <source-image>", file=sys.stderr)
        sys.exit(2)
    
    source_image = sys.argv[1]
    mirror_image = get_mirror_image(source_image)
    
    print(f"Checking if {source_image} is up to date in mirror...", file=sys.stderr)
    print(f"Source: {source_image}", file=sys.stderr)
    print(f"Mirror: {mirror_image}", file=sys.stderr)
    
    # First check if mirror image exists
    if not image_exists(mirror_image):
        print(f"Mirror image {mirror_image} doesn't exist", file=sys.stderr)
        sys.exit(1)  # Not latest - mirror doesn't exist
    
    # Get digests
    source_digest = get_image_digest(source_image)
    mirror_digest = get_image_digest(mirror_image)
    
    if not source_digest or not mirror_digest:
        print("Failed to get digests for comparison", file=sys.stderr)
        sys.exit(1)  # Error, assume not latest
    
    print(f"Source digest: {source_digest}", file=sys.stderr)
    print(f"Mirror digest: {mirror_digest}", file=sys.stderr)
    
    # Compare digests
    if source_digest == mirror_digest:
        print(f"✓ Image {source_image} is up to date in the mirror", file=sys.stderr)
        sys.exit(0)  # True - is latest
    else:
        print(f"✗ Image {source_image} needs to be updated in the mirror", file=sys.stderr)
        sys.exit(1)  # False - not latest

if __name__ == '__main__':
    main()