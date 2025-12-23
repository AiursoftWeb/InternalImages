#!/usr/bin/env python3
import sys
import os
import subprocess

def get_mirror_image(source_image):
    """Convert a source image name to its mirror equivalent."""
    registry = os.environ.get('MIRROR_TARGET', 'hub.aiursoft.com')
    
    if ':' in source_image:
        repo_part, tag = source_image.rsplit(':', 1)
    else:
        repo_part = source_image
        tag = "latest"
    
    # Handle Docker Hub images
    if '/' not in repo_part:
        mirror_repo = f"{repo_part}"
    else:
        mirror_repo = repo_part
    
    return f"{registry}/{mirror_repo}:{tag}"

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
        return None
    except Exception:
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
        sys.exit(2)
    
    source_image = sys.argv[1]
    mirror_image = get_mirror_image(source_image)
    
    # Check if mirror exists
    if not image_exists(mirror_image):
        sys.exit(1)
    
    # Get and compare digests
    source_digest = get_image_digest(source_image)
    mirror_digest = get_image_digest(mirror_image)
    
    if not source_digest or not mirror_digest:
        sys.exit(1)
    
    # Exit 0 if digests match (is latest), 1 otherwise
    sys.exit(0 if source_digest == mirror_digest else 1)

if __name__ == '__main__':
    main()