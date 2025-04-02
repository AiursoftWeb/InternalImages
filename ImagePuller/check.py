#!/usr/bin/env python3
import sys
import requests

def check_image(image):
    """
    检查 image 是否正常。
    image 格式应为：hub.aiursoft.cn/<repository>:<tag>
    """
    registry = "hub.aiursoft.cn"
    if not image.startswith(f"{registry}/"):
        print("Image 不属于目标 registry", file=sys.stderr)
        return False

    try:
        rest = image[len(f"{registry}/"):]
        repository, tag = rest.rsplit(":", 1)
    except ValueError:
        print("镜像格式错误", file=sys.stderr)
        return False

    # 先尝试通过 tag 获取 manifest
    url_tag = f"https://{registry}/v2/{repository}/manifests/{tag}"
    # -H "Authorization: Bearer QQ==" -H 'Accept: application/vnd.oci.image.index.v1+json'
    resp = requests.get(url_tag, headers={
        'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
    })
    if not resp.ok:
        print(f"{url_tag} 获取 manifest 失败: {repository}:{tag}. Status Code: {resp.status_code}", file=sys.stderr)
            #   ", file=sys.stderr)
        return False

    try:
        data = resp.json()
    except Exception as e:
        print("解析 JSON 失败", file=sys.stderr)
        return False

    # 如果返回的数据中包含 manifests 字段，则按 digest 再次验证
    if "manifests" in data:
        try:
            digest = data["manifests"][0]["digest"]
        except (IndexError, KeyError):
            print("manifest 数据异常", file=sys.stderr)
            return False

        url_digest = f"https://{registry}/v2/{repository}/manifests/{digest}"
        resp_digest = requests.get(url_digest, headers={
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'
        })
        if not resp_digest.ok:
            print(f"{url_digest} 通过 digest 获取 manifest 失败: {repository}:{tag}. Status Code: {resp_digest.status_code}", file=sys.stderr)
            return False

    if "manifests" in data:
        print(f"获取到的 manifest 数据中包含 manifests 字段，这意味着该镜像是一个融合的镜像.", file=sys.stderr)
        return True
    elif "layers" in data:    
        print(f"获取到的 manifest 数据中不包含 manifests 字段，但包含 layers 字段。 URL: {url_tag}. 这意味着该镜像是一个单架构映像而不是一个融合的镜像.", file=sys.stderr)
        return True
    else:
        print(f"获取到的 manifest 数据中不包含 manifests 字段和 layers 字段. URL: {url_tag}. 这意味着可能出错了！", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 2:
        print("用法: check.py <image>", file=sys.stderr)
        sys.exit(2)

    image = sys.argv[1]
    if check_image(image):
        print(f"Image {image} 正常", file=sys.stderr)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
