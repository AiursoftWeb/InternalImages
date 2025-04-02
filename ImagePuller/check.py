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
    resp = requests.get(url_tag)
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
        resp_digest = requests.get(url_digest)
        if not resp_digest.ok:
            print(f"通过 digest 获取 manifest 失败: {repository}:{tag}", file=sys.stderr)
            return False

    return True

def main():
    if len(sys.argv) < 2:
        print("用法: check.py <image>", file=sys.stderr)
        sys.exit(2)

    image = sys.argv[1]
    if check_image(image):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
